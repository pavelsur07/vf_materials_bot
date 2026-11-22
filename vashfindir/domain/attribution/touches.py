import re
from datetime import datetime, timedelta
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, LeadMagnet, Touch, User
from vashfindir.domain.attribution.dto import UTM_FIELDS, MagnetContent, StartRequest, StartResult
from vashfindir.domain.attribution.settings import AttributionPreferences
from vashfindir.domain.jobs import utcnow

_PAYLOAD = re.compile(r"[A-Za-z0-9_-]{1,64}")


async def _describe(session: AsyncSession, touch: Touch, *, duplicate: bool) -> StartResult:
    magnet = await session.get(LeadMagnet, touch.lead_magnet_id) if touch.lead_magnet_id else None
    return StartResult(
        touch_id=touch.id,
        code_status=touch.code_status,
        raw_payload=touch.raw_payload,
        created_at=touch.created_at,
        magnet_source=touch.magnet_source,
        magnet=MagnetContent.model_validate(magnet) if magnet and magnet.is_active else None,
        duplicate=duplicate,
    )


async def register_touch(
    session: AsyncSession,
    data: StartRequest,
    preferences: AttributionPreferences | None = None,
    *,
    now: datetime | None = None,
) -> StartResult:
    now = now or utcnow()
    preferences = preferences or AttributionPreferences()
    payload = data.payload or None
    digest = sha256((payload or "").encode()).hexdigest()
    async with session.begin():
        profile = data.model_dump(exclude={"payload"})
        statement = insert(User).values(**profile, first_seen_at=now, last_seen_at=now)
        new_id = await session.scalar(
            statement.on_conflict_do_nothing(index_elements=[User.tg_id]).returning(User.id)
        )
        user = (await session.scalars(select(User).where(User.tg_id == data.tg_id))).one()
        user.username = data.username
        user.first_name = data.first_name
        user.last_name = data.last_name
        user.is_blocked = False
        user.first_seen_at = user.first_seen_at or user.created_at
        user.last_seen_at = max(user.last_seen_at or now, now)

        if preferences.dedup_minutes:
            since = now - timedelta(minutes=preferences.dedup_minutes)
            previous = await session.scalar(
                select(Touch)
                .where(
                    Touch.tg_id == data.tg_id,
                    Touch.payload_digest == digest,
                    Touch.created_at > since,
                    Touch.is_test == (data.tg_id in preferences.test_ids),
                )
                .order_by(Touch.id.desc())
                .limit(1)
            )
            if previous is not None:
                return await _describe(session, previous, duplicate=True)

        touch = Touch(
            tg_id=data.tg_id,
            raw_payload=payload[:64] if payload else None,
            payload_digest=digest,
            created_at=now,
            code_status="direct" if not payload else "unknown",
            utm_source="direct" if not payload else "unknown",
            is_new_user=new_id is not None,
            is_test=data.tg_id in preferences.test_ids,
        )
        if payload and _PAYLOAD.fullmatch(payload):
            link = await session.scalar(
                select(AttributionLink).where(AttributionLink.code == payload)
            )
            if link is not None:
                touch.code_status = "ok"
                touch.link_id = link.id
                touch.lead_magnet_id = link.lead_magnet_id
                touch.magnet_source = "link"
                for field in UTM_FIELDS:
                    setattr(touch, field, getattr(link, field))
            else:
                magnet_id = await session.scalar(
                    select(LeadMagnet.id).where(LeadMagnet.prefix == payload.partition("_")[0])
                )
                if magnet_id is not None:
                    touch.lead_magnet_id = magnet_id
                    touch.magnet_source = "prefix"
        session.add(touch)
        await session.flush()
        if user.first_touch_id is None:
            user.first_touch_id = touch.id
        user.last_touch_id = touch.id
        return await _describe(session, touch, duplicate=False)


async def get_touch(session: AsyncSession, tg_id: int, touch_id: int) -> StartResult | None:
    async with session.begin():
        touch = await session.get(Touch, touch_id)
        if touch is None or touch.tg_id != tg_id:
            return None
        return await _describe(session, touch, duplicate=True)


async def select_magnet(
    session: AsyncSession, tg_id: int, touch_id: int, magnet_id: int
) -> MagnetContent | None:
    async with session.begin():
        await session.execute(
            update(Touch).where(Touch.id == touch_id, Touch.tg_id == tg_id).values(id=Touch.id)
        )
        touch = await session.get(Touch, touch_id, populate_existing=True)
        if touch is None or touch.tg_id != tg_id:
            return None
        magnet = await session.get(LeadMagnet, magnet_id)
        if magnet is None or not magnet.is_active:
            return None
        if touch.lead_magnet_id == magnet_id and touch.magnet_delivered:
            return MagnetContent.model_validate(magnet)
        if touch.lead_magnet_id != magnet_id and (
            touch.magnet_delivered or touch.magnet_source == "menu"
        ):
            return None
        touch.lead_magnet_id = magnet_id
        touch.magnet_source = "menu"
        return MagnetContent.model_validate(magnet)


async def finish_delivery(
    session: AsyncSession,
    tg_id: int,
    touch_id: int,
    *,
    delivered: bool = False,
    blocked: bool = False,
) -> None:
    async with session.begin():
        values = {"delivery_finished": True}
        if delivered:
            values["magnet_delivered"] = True
        await session.execute(
            update(Touch).where(Touch.id == touch_id, Touch.tg_id == tg_id).values(**values)
        )
        if blocked:
            await session.execute(update(User).where(User.tg_id == tg_id).values(is_blocked=True))
