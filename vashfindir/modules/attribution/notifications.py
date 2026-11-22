import json
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import Job
from vashfindir.domain.attribution.dto import MagnetContent, StartResult
from vashfindir.domain.attribution.settings import get_preferences
from vashfindir.domain.attribution.summary import (
    DailySummary,
    build_summary,
    local_datetime,
    mark_summary_sent,
    summary_is_sent,
)
from vashfindir.domain.jobs import utcnow
from vashfindir.integrations.telegram_delivery import TelegramDelivery


def _render_summary(summary: DailySummary, warning_threshold: int) -> list[str]:
    total = summary.total or 1
    lines = [
        f"Сводка за {summary.day:%d.%m.%Y}",
        f"Касаний: {summary.total}. Новых пользователей: {summary.new_users}.",
        f"Без кода: {summary.direct} ({100 * summary.direct / total:.1f}%).",
        f"Неизвестных кодов: {summary.unknown} ({100 * summary.unknown / total:.1f}%).",
        f"Ошибок Bitrix24: {summary.errors}.",
        "",
        "Выдачи по материалам:",
    ]
    lines.extend(f"• {magnet.name}: {magnet.count}" for magnet in summary.magnets)
    if not summary.magnets:
        lines.append("Выдач за сутки нет.")
    if summary.empty_links:
        lines.extend(("", "Активные ссылки без касаний за первые 7 дней:"))
        lines.extend(f"• {link.code} — {link.placement}" for link in summary.empty_links)
    if summary.direct_unknown_percent > warning_threshold:
        lines.extend(
            (
                "",
                f"Предупреждение: без кода и с неизвестным кодом за 7 дней "
                f"{summary.direct_unknown_percent:.1f}% при пороге {warning_threshold}%.",
            )
        )
    messages: list[str] = []
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 1800:
            messages.append(chunk.rstrip())
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        messages.append(chunk.rstrip())
    return messages


class AttributionNotifications:
    def __init__(self, bootstrap_admins: list[int], telegram: TelegramDelivery) -> None:
        self._bootstrap_admins = bootstrap_admins
        self._telegram = telegram

    async def _send(self, session: AsyncSession, text: str) -> None:
        async with session.begin():
            prefs = await get_preferences(session, self._bootstrap_admins)
        if prefs.service_chat_id:
            await self._telegram.notify(prefs.service_chat_id, text)

    async def unknown(
        self,
        session: AsyncSession,
        touch: StartResult,
        username: str | None,
        delivered: bool,
    ) -> None:
        if touch.code_status != "unknown" or touch.duplicate:
            return
        username_text = f"@{username}" if username else "без username"
        result = "да" if delivered and touch.magnet_source == "prefix" else "нет"
        await self._send(
            session,
            f"Неизвестный код: {touch.raw_payload!r}. Пользователь: {username_text}.\n"
            f"Время: {touch.created_at:%Y-%m-%d %H:%M:%S} UTC. Выдача по префиксу: {result}.",
        )

    async def file_error(
        self,
        session: AsyncSession,
        magnet: MagnetContent,
        reason: str,
    ) -> None:
        await self._send(
            session, f"Не удалось отправить файл {magnet.prefix} ({magnet.name}). {reason}"
        )

    async def bitrix(
        self,
        session: AsyncSession,
        touch_id: int,
        error: str | None,
        old_lead: int | None,
        new_lead: int | None,
    ) -> None:
        if old_lead is not None and new_lead is not None:
            await self._send(
                session, f"Лид Bitrix24 пересоздан. Старый ID {old_lead}, новый {new_lead}."
            )
        if error:
            await self._send(session, f"Ошибка Bitrix24. Касание {touch_id}. {error}.")

    async def summary_job(self, job: Job, session: AsyncSession) -> None:
        scheduled_day = date.fromisoformat(json.loads(job.payload)["day"])
        async with session.begin():
            prefs = await get_preferences(session, self._bootstrap_admins)
            zone = ZoneInfo(prefs.timezone)
            local = local_datetime(utcnow(), zone)
            if (
                not prefs.service_chat_id
                or scheduled_day != local.date()
                or local.time() < prefs.summary_time
                or await summary_is_sent(session, scheduled_day)
            ):
                return
            summary = await build_summary(session, scheduled_day - timedelta(days=1), zone)

        for message in _render_summary(summary, prefs.warning_percent):
            if not await self._telegram.notify(prefs.service_chat_id, message):
                raise RuntimeError("Telegram did not accept the attribution summary")
        async with session.begin():
            await mark_summary_sent(session, scheduled_day)
