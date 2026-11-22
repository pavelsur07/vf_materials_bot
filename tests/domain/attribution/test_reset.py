from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AuditLog, Job, Touch, User
from vashfindir.domain.attribution.bitrix_queue import BITRIX_JOB
from vashfindir.domain.attribution.dto import StartRequest
from vashfindir.domain.attribution.settings import AttributionPreferences, save_preferences
from vashfindir.domain.attribution.touches import register_touch
from vashfindir.domain.jobs import enqueue_job

TESTER = AttributionPreferences(admin_ids=[7], test_ids=[123])


async def test_reset_deletes_test_activity_and_preserves_other_users(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.reset import reset_test_user

    await session.execute(text("PRAGMA foreign_keys=ON"))
    await session.commit()
    async with session.begin():
        await save_preferences(session, TESTER, [7], 7)
    regular = await register_touch(session, StartRequest(tg_id=456, first_name="Клиент"))
    old = await register_touch(session, StartRequest(tg_id=123, first_name="Тест"), TESTER)
    async with session.begin():
        await enqueue_job(session, BITRIX_JOB, {"touch_id": old.touch_id})
    async with session.begin():
        outcome = await reset_test_user(session, 123, [7], actor=7)
    assert outcome == 1
    assert await session.get(Touch, old.touch_id) is None
    assert await session.get(Touch, regular.touch_id) is not None
    assert len((await session.scalars(select(Job))).all()) == 0
    audit = (await session.scalars(select(AuditLog).where(AuditLog.entity == "test_user"))).one()
    assert audit.actor_tg_id == 7 and audit.entity_id == "123"
    assert (await session.scalars(select(User.tg_id))).all() == [456]
    await session.commit()
    new = await register_touch(session, StartRequest(tg_id=123, first_name="Тест"), TESTER)
    assert new.touch_id > old.touch_id
    row = await session.get(Touch, new.touch_id)
    assert row.is_new_user and row.is_test


async def test_reset_rejects_mixed_history_and_normal_ids(session: AsyncSession) -> None:
    import pytest

    from vashfindir.domain.attribution.reset import ResetError, reset_test_user

    async with session.begin():
        await save_preferences(session, TESTER, [7], 7)
    await register_touch(
        session, StartRequest(tg_id=123, first_name="Клиент"), AttributionPreferences()
    )
    await register_touch(session, StartRequest(tg_id=123, first_name="Тест"), TESTER)
    for tg_id in (123, 456):
        with pytest.raises(ResetError):
            async with session.begin():
                await reset_test_user(session, tg_id, [7], actor=7)
    assert len((await session.scalars(select(Touch))).all()) == 2


async def test_reset_does_not_race_with_running_crm_job(session: AsyncSession) -> None:
    import pytest

    from vashfindir.domain.attribution.reset import ResetError, reset_test_user

    async with session.begin():
        await save_preferences(session, TESTER, [7], 7)
    touch = await register_touch(session, StartRequest(tg_id=123, first_name="Тест"), TESTER)
    async with session.begin():
        job = await enqueue_job(session, BITRIX_JOB, {"touch_id": touch.touch_id})
        job.status = "running"
    with pytest.raises(ResetError):
        async with session.begin():
            await reset_test_user(session, 123, [7], actor=7)
    assert await session.get(Touch, touch.touch_id) is not None
