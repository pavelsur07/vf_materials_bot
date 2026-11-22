from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, Job, LeadMagnet, Touch
from vashfindir.domain.attribution.dto import StartRequest
from vashfindir.domain.attribution.settings import AttributionPreferences, save_preferences
from vashfindir.domain.attribution.touches import finish_delivery, register_touch


async def test_summary_uses_local_day_and_excludes_test_touches(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.summary import build_summary

    now = datetime(2026, 11, 22, 21, 15)
    magnet = LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Text")
    session.add(magnet)
    await session.flush()
    session.add_all(
        [
            AttributionLink(
                code="dds_001",
                lead_magnet_id=magnet.id,
                utm_source="tg",
                utm_medium="post",
                utm_campaign="active",
                placement="Канал",
                created_by=1,
                period_start=date(2026, 11, 17),
            ),
            AttributionLink(
                code="dds_002",
                lead_magnet_id=magnet.id,
                utm_source="tg",
                utm_medium="post",
                utm_campaign="quiet",
                placement="Партнёр",
                created_by=1,
                period_start=date(2026, 11, 17),
            ),
        ]
    )
    await session.commit()
    direct = await register_touch(session, StartRequest(tg_id=234, first_name="Иван"), now=now)
    reply = await register_touch(
        session,
        StartRequest(tg_id=235, first_name="Илья", payload="dds_001"),
        now=now,
    )
    await finish_delivery(session, 235, reply.touch_id, delivered=True)
    await register_touch(
        session,
        StartRequest(tg_id=236, first_name="Тест", payload="dds_002"),
        AttributionPreferences(test_ids=[236]),
        now=now,
    )
    error = await session.get(Touch, direct.touch_id)
    error.bitrix_status = "error"
    await session.commit()

    result = await build_summary(session, date(2026, 11, 23), ZoneInfo("Europe/Moscow"))
    assert (result.total, result.new_users, result.direct, result.unknown, result.errors) == (
        2,
        2,
        1,
        0,
        1,
    )
    assert [(item.name, item.count) for item in result.magnets] == [("ДДС", 1)]
    assert result.direct_unknown_percent == 50
    assert [item.code for item in result.empty_links] == ["dds_002"]


async def test_daily_job_is_scheduled_once_when_local_time_arrives(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.summary import enqueue_daily_summary, mark_summary_sent

    async with session.begin():
        await save_preferences(
            session,
            AttributionPreferences(admin_ids=[1], service_chat_id=-123),
            [1],
            1,
        )
    before = datetime(2026, 11, 23, 5, 59)
    due = datetime(2026, 11, 23, 6, 0)
    async with session.begin():
        assert not await enqueue_daily_summary(session, [1], before)
        assert await enqueue_daily_summary(session, [1], due)
        assert not await enqueue_daily_summary(session, [1], due)
        await mark_summary_sent(session, date(2026, 11, 23))
    assert len((await session.scalars(select(Job))).all()) == 1


async def test_unknown_notification_reports_prefix_delivery(session: AsyncSession) -> None:
    from unittest.mock import AsyncMock

    from vashfindir.domain.attribution.dto import StartResult
    from vashfindir.modules.attribution.notifications import AttributionNotifications

    async with session.begin():
        await save_preferences(
            session,
            AttributionPreferences(admin_ids=[1], service_chat_id=-123),
            [1],
            1,
        )
    delivery = AsyncMock()
    notifier = AttributionNotifications([1], delivery)
    touch = StartResult(
        touch_id=1,
        code_status="unknown",
        raw_payload="dds_123",
        created_at=datetime(2026, 11, 23, 6),
        magnet_source="prefix",
        magnet=None,
    )
    await notifier.unknown(session, touch, "example", True)
    await notifier.unknown(session, touch.model_copy(update={"duplicate": True}), "example", True)
    delivery.notify.assert_awaited_once()
    chat_id, message = delivery.notify.await_args.args
    assert chat_id == -123
    assert "dds_123" in message and "@example" in message
    assert "Выдача по префиксу: да" in message
