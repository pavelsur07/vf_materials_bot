import json
from datetime import datetime

from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import Job
from vashfindir.domain.attribution.bitrix_queue import (
    BitrixWork,
    enqueue_due_touches,
    fail_touch,
    get_work,
    save_lead_id,
    succeed_touch,
)
from vashfindir.domain.attribution.bitrix_settings import (
    BitrixConnection,
    BitrixSettingsError,
    load_connection,
)
from vashfindir.domain.jobs import utcnow
from vashfindir.integrations.bitrix24 import BitrixClient, BitrixError
from vashfindir.modules.attribution.notifications import AttributionNotifications

_ORIGINATOR = "vashfindir_materials"


class SyncEvent(BaseModel):
    touch_id: int
    error: str | None = None
    old_lead: int | None = None
    new_lead: int | None = None


async def _connection(session: AsyncSession, key: SecretStr) -> BitrixConnection | None:
    try:
        return await load_connection(session, key)
    except BitrixSettingsError:
        return None


async def enqueue_bitrix_work(session: AsyncSession, key: SecretStr) -> int:
    async with session.begin():
        if await _connection(session, key) is None:
            return 0
        return await enqueue_due_touches(session, utcnow())


class BitrixSync:
    def __init__(
        self,
        gateway: BitrixClient,
        key: SecretStr,
        notifications: AttributionNotifications | None = None,
    ) -> None:
        self._gateway = gateway
        self._key = key
        self._notifications = notifications

    async def _ensure_lead(
        self,
        session: AsyncSession,
        connection: BitrixConnection,
        work: BitrixWork,
        *,
        deleted_lead: int | None = None,
    ) -> int:
        origin_id = f"test-{work.first_touch_id}" if work.is_test else f"tg-{work.tg_id}"
        lead_id = await self._gateway.find_lead(connection.webhook, _ORIGINATOR, origin_id)
        if lead_id is not None and lead_id == deleted_lead:
            raise BitrixError("deleted_lead_still_listed")
        if lead_id is None:
            fields = connection.fields
            prefix = "[ТЕСТ] " if work.is_test else ""
            title = f"{prefix}Telegram: {work.first_name or work.tg_id}"
            if work.first_magnet:
                title = f"{title} — {work.first_magnet}"
            lead_id = await self._gateway.add_lead(
                connection.webhook,
                {
                    "TITLE": title,
                    "NAME": work.first_name,
                    "LAST_NAME": work.last_name,
                    "SOURCE_ID": fields.source_id,
                    "ORIGINATOR_ID": _ORIGINATOR,
                    "ORIGIN_ID": origin_id,
                    **work.first_utm,
                    fields.telegram_id: work.tg_id,
                    fields.telegram_username: work.username,
                    fields.first_touch: work.first_code,
                    fields.last_touch: work.last_code,
                    fields.magnets: work.delivered_magnets,
                },
            )
        async with session.begin():
            await save_lead_id(session, work.tg_id, lead_id)
        return lead_id

    async def handle_touch(
        self,
        session: AsyncSession,
        touch_id: int,
        *,
        now: datetime | None = None,
    ) -> SyncEvent | None:
        started_at = now or utcnow()
        async with session.begin():
            connection = await _connection(session, self._key)
            work = await get_work(session, touch_id, started_at) if connection else None
        if connection is None or work is None:
            return None

        old_lead: int | None = None
        new_lead: int | None = None
        comment_id = work.comment_id
        try:
            fields = connection.fields
            update_fields: dict[str, object] = {
                fields.last_touch: work.last_code,
                fields.magnets: work.delivered_magnets,
            }
            lead_id = work.lead_id
            if lead_id is None:
                lead_id = await self._ensure_lead(session, connection, work)
            else:
                try:
                    await self._gateway.update_lead(connection.webhook, lead_id, update_fields)
                except BitrixError as exc:
                    if not exc.not_found:
                        raise
                    old_lead = lead_id
                    lead_id = await self._ensure_lead(
                        session, connection, work, deleted_lead=old_lead
                    )
                    new_lead = lead_id
                    comment_id = None

            if work.touch_id != work.first_touch_id and comment_id is None:
                marker = f"[касание #{touch_id}]"
                if work.attempts:
                    comment_id = await self._gateway.find_comment(
                        connection.webhook, lead_id, marker
                    )
                if comment_id is None:
                    magnet = work.current_magnet or "без материала"
                    timestamp = work.current_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                    comment_id = await self._gateway.add_comment(
                        connection.webhook,
                        lead_id,
                        f"Повторное касание: {work.current_code}, {magnet}, {timestamp} {marker}",
                    )
        except BitrixError as exc:
            error = str(exc)
            async with session.begin():
                exhausted = await fail_touch(
                    session,
                    work,
                    error,
                    exc.retry_after,
                    now or utcnow(),
                )
            return SyncEvent(
                touch_id=touch_id,
                error=error if exhausted else None,
                old_lead=old_lead,
                new_lead=new_lead,
            )

        async with session.begin():
            await succeed_touch(session, work, comment_id)
        return SyncEvent(touch_id=touch_id, old_lead=old_lead, new_lead=new_lead)

    async def handle_job(self, job: Job, session: AsyncSession) -> None:
        raw = json.loads(job.payload)
        if not isinstance(raw, dict):
            raise ValueError("Invalid Bitrix job payload")
        touch_id = raw.get("touch_id")
        if isinstance(touch_id, bool) or not isinstance(touch_id, int) or touch_id <= 0:
            raise ValueError("Invalid Bitrix touch identifier")
        event = await self.handle_touch(session, touch_id)
        if event is not None and self._notifications is not None:
            await self._notifications.bitrix(
                session,
                event.touch_id,
                event.error,
                event.old_lead,
                event.new_lead,
            )
