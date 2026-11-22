from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import Job, Touch, User
from vashfindir.domain.attribution.bitrix_settings import BitrixFields, save_connection
from vashfindir.domain.attribution.dto import StartRequest
from vashfindir.domain.attribution.touches import finish_delivery, register_touch

KEY = SecretStr("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
FIELDS = BitrixFields(
    source_id="TELEGRAM",
    telegram_id="UF_CRM_TG_ID",
    telegram_username="UF_CRM_USERNAME",
    first_touch="UF_CRM_FIRST",
    last_touch="UF_CRM_LAST",
    magnets="UF_CRM_MAGNETS",
)


async def configure(session: AsyncSession) -> None:
    async with session.begin():
        await save_connection(
            session, KEY, FIELDS, SecretStr("https://example.bitrix24.ru/rest/15/test-key/"), 10
        )


async def test_pending_catches_up_after_webhook_saved(session: AsyncSession) -> None:
    from vashfindir.modules.attribution.bitrix_sync import enqueue_bitrix_work

    touch = await register_touch(session, StartRequest(tg_id=100, first_name="Иван"))
    await finish_delivery(session, 100, touch.touch_id)
    assert await enqueue_bitrix_work(session, KEY) == 0
    pending = await session.get(Touch, touch.touch_id)
    assert pending.bitrix_attempts == 0 and pending.bitrix_status == "pending"
    await session.commit()
    await configure(session)
    assert await enqueue_bitrix_work(session, KEY) == 1
    assert await enqueue_bitrix_work(session, KEY) == 0
    assert len((await session.scalars(select(Job))).all()) == 1


async def test_one_lead_first_fields_immutable_and_repeat_timeline(session: AsyncSession) -> None:
    from vashfindir.modules.attribution.bitrix_sync import BitrixSync

    await configure(session)
    now = datetime(2026, 11, 22, 12)
    request = StartRequest(tg_id=100, first_name="Иван", last_name="Иванов", username="example")
    first = await register_touch(session, request, now=now)
    second = await register_touch(
        session, request.model_copy(update={"payload": "mistake"}), now=now + timedelta(minutes=1)
    )
    transport = AsyncMock()
    transport.find_lead.return_value = None
    transport.add_lead.return_value = 543
    transport.add_comment.return_value = 8
    sync = BitrixSync(transport, KEY)
    await sync.handle_touch(session, first.touch_id)
    await sync.handle_touch(session, second.touch_id)
    transport.add_lead.assert_awaited_once()
    add = transport.add_lead.await_args.args[1]
    assert add["UTM_SOURCE"] == "direct"
    assert add["UF_CRM_FIRST"] == "direct"
    assert add["UF_CRM_TG_ID"] == 100
    assert add["UF_CRM_USERNAME"] == "@example"
    assert transport.update_lead.await_args.args[1:] == (
        543,
        {"UF_CRM_LAST": "unknown:mistake", "UF_CRM_MAGNETS": ""},
    )
    transport.add_comment.assert_awaited_once()
    assert "Повторное касание: unknown:mistake" in transport.add_comment.await_args.args[2]
    stored = await session.get(User, 1)
    assert stored.bitrix_lead_id == 543


async def test_deleted_lead_is_recreated_with_first_touch(session: AsyncSession) -> None:
    from vashfindir.integrations.bitrix24 import BitrixError
    from vashfindir.modules.attribution.bitrix_sync import BitrixSync

    await configure(session)
    now = datetime(2026, 11, 22, 12)
    request = StartRequest(tg_id=100, first_name="Иван")
    first = await register_touch(session, request, now=now)
    second = await register_touch(
        session, request.model_copy(update={"payload": "second"}), now=now + timedelta(minutes=1)
    )
    transport = AsyncMock()
    transport.find_lead.return_value = None
    transport.add_lead.side_effect = [543, 544]
    transport.update_lead.side_effect = BitrixError("lead_not_found", not_found=True)
    transport.add_comment.return_value = 9
    sync = BitrixSync(transport, KEY)
    await sync.handle_touch(session, first.touch_id)
    await sync.handle_touch(session, second.touch_id)
    user = await session.get(User, 1)
    assert user.bitrix_lead_id == 544
    assert transport.add_lead.await_args.args[1]["UTM_SOURCE"] == "direct"
    assert transport.add_lead.await_args.args[1]["UF_CRM_FIRST"] == "direct"


async def test_five_retries_then_error(session: AsyncSession) -> None:
    from vashfindir.integrations.bitrix24 import BitrixError
    from vashfindir.modules.attribution.bitrix_sync import BitrixSync

    await configure(session)
    first = await register_touch(session, StartRequest(tg_id=100, first_name="Иван"))
    transport = AsyncMock()
    transport.find_lead.side_effect = BitrixError("network_error")
    sync = BitrixSync(transport, KEY)
    now = datetime(2026, 11, 22, 12)
    for minutes in [1, 5, 15, 60, 240]:
        await sync.handle_touch(session, first.touch_id, now=now)
        row = await session.get(Touch, first.touch_id)
        assert row.bitrix_status == "pending"
        assert row.bitrix_next_attempt_at == now + timedelta(minutes=minutes)
        await session.commit()
        now += timedelta(minutes=minutes)
    await sync.handle_touch(session, first.touch_id, now=now)
    row = await session.get(Touch, first.touch_id)
    assert row.bitrix_status == "error"
    assert row.bitrix_attempts == 6
    assert row.bitrix_next_attempt_at is None
    assert "network_error" in row.bitrix_error


async def test_reset_creates_distinct_test_lead_without_reusing_old_origin(
    session: AsyncSession,
) -> None:
    from vashfindir.domain.attribution.reset import reset_test_user
    from vashfindir.domain.attribution.settings import AttributionPreferences, save_preferences
    from vashfindir.modules.attribution.bitrix_sync import BitrixSync

    await configure(session)
    async with session.begin():
        await save_preferences(
            session, AttributionPreferences(admin_ids=[10], test_ids=[100]), [10], 10
        )
    request = StartRequest(tg_id=100, first_name="Тест")
    transport = AsyncMock()
    transport.find_lead.return_value = None
    transport.add_lead.side_effect = [543, 544]
    sync = BitrixSync(transport, KEY)
    first = await register_touch(session, request)
    await sync.handle_touch(session, first.touch_id)
    async with session.begin():
        assert await reset_test_user(session, 100, [10], actor=10) == 1
    second = await register_touch(session, request)
    await sync.handle_touch(session, second.touch_id)
    one, two = [call.args[1] for call in transport.add_lead.await_args_list]
    assert one["TITLE"] == two["TITLE"] == "[ТЕСТ] Telegram: Тест"
    assert one["ORIGIN_ID"] != two["ORIGIN_ID"]
