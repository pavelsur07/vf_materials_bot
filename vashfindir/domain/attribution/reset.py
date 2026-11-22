from sqlalchemy import Integer, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import Job, Touch, User
from vashfindir.domain.attribution.audit import record_change
from vashfindir.domain.attribution.bitrix_queue import BITRIX_JOB
from vashfindir.domain.attribution.settings import get_preferences
from vashfindir.domain.jobs import JobStatus


class ResetError(ValueError):
    pass


async def test_accounts(session: AsyncSession, ids: list[int]) -> dict[int, User]:
    return {
        user.tg_id: user
        for user in (await session.scalars(select(User).where(User.tg_id.in_(ids)))).all()
    }


async def reset_test_user(
    session: AsyncSession,
    tg_id: int,
    bootstrap_admins: list[int],
    *,
    actor: int,
) -> int | None:
    if not 0 < tg_id < 2**63:
        raise ResetError("Укажите Telegram ID тестового пользователя.")

    # A concurrent queue claim or /start must finish before the safety checks.
    await session.execute(update(User).where(User.tg_id == tg_id).values(id=User.id))
    prefs = await get_preferences(session, bootstrap_admins)
    if tg_id not in prefs.test_ids:
        raise ResetError("Этот Telegram ID отсутствует в списке тестовых пользователей.")

    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        return None
    if (
        await session.scalar(
            select(Touch.id)
            .where(
                Touch.tg_id == tg_id,
                Touch.is_test.is_(False),
            )
            .limit(1)
        )
        is not None
    ):
        raise ResetError("У этого пользователя есть боевые касания. Сброс остановлен.")

    touch_ids = select(Touch.id).where(Touch.tg_id == tg_id, Touch.is_test.is_(True))
    bitrix_jobs = (
        Job.type == BITRIX_JOB,
        cast(func.json_extract(Job.payload, "$.touch_id"), Integer).in_(touch_ids),
    )
    if (
        await session.scalar(
            select(Job.id)
            .where(
                *bitrix_jobs,
                Job.status == JobStatus.RUNNING,
            )
            .limit(1)
        )
        is not None
    ):
        raise ResetError("Сейчас обрабатывается отправка в Bitrix24. Повторите сброс позже.")
    await session.execute(delete(Job).where(*bitrix_jobs))
    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            first_touch_id=None,
            last_touch_id=None,
        )
    )
    removed = await session.scalars(
        delete(Touch)
        .where(
            Touch.tg_id == tg_id,
            Touch.is_test.is_(True),
        )
        .returning(Touch.id)
    )
    count = len(removed.all())
    await session.delete(user)
    record_change(
        session,
        actor,
        "test_user",
        tg_id,
        {"registered": True, "removed_touches": 0, "bitrix_lead_id": user.bitrix_lead_id},
        {"registered": False, "removed_touches": count, "bitrix_lead_id": user.bitrix_lead_id},
    )
    return count
