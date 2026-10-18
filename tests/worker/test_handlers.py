from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Job, User
from bot.services.jobs import JobStatus, claim_due_job, enqueue_job, utcnow
from bot.worker.handlers import DAILY_STATS, DAILY_STATS_INTERVAL, HANDLERS


async def test_daily_stats_handler_reschedules_itself(session: AsyncSession) -> None:
    session.add(User(tg_id=42, username="u", first_name="f"))
    await session.commit()
    current = await enqueue_job(session, DAILY_STATS)
    claimed = await claim_due_job(session)
    assert claimed is not None

    await HANDLERS[DAILY_STATS](claimed, session)

    result = await session.scalars(
        select(Job).where(Job.type == DAILY_STATS, Job.status == JobStatus.PENDING)
    )
    scheduled = list(result)
    assert len(scheduled) == 1
    assert scheduled[0].id != current.id
    assert scheduled[0].run_at >= utcnow() + DAILY_STATS_INTERVAL - timedelta(minutes=1)
