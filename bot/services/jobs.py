import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Job


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


def utcnow() -> datetime:
    # SQLite хранит наивные строки и CURRENT_TIMESTAMP без таймзоны: сравнения
    # с func.now() лексикографические, поэтому в коде тоже наивный UTC.
    return datetime.now(UTC).replace(tzinfo=None)


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    payload: dict[str, Any] | None = None,
    run_at: datetime | None = None,
) -> Job:
    job = Job(
        type=job_type,
        payload=json.dumps(payload or {}, ensure_ascii=False),
        run_at=run_at or utcnow(),
    )
    session.add(job)
    await session.commit()
    return job


async def ensure_scheduled(
    session: AsyncSession,
    job_type: str,
    interval: timedelta,
    payload: dict[str, Any] | None = None,
) -> Job | None:
    """Поставить задачу на now+interval, если нет pending/running такого типа."""
    result = await session.execute(
        select(Job.id)
        .where(
            Job.type == job_type,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return None
    return await enqueue_job(session, job_type, payload, run_at=utcnow() + interval)


async def claim_due_job(session: AsyncSession) -> Job | None:
    """Атомарно забрать старейшую подошедшую pending-задачу. None — очередь пуста."""
    result = await session.execute(
        select(Job.id)
        .where(Job.status == JobStatus.PENDING, Job.run_at <= utcnow())
        .order_by(Job.id)
        .limit(1)
    )
    job_id = result.scalar_one_or_none()
    if job_id is None:
        return None
    # UPDATE с проверкой статуса: если между SELECT и UPDATE задачу забрал другой
    # процесс, rowcount будет 0 и мы не выполним её дважды.
    claimed = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.PENDING)
        .values(status=JobStatus.RUNNING, attempts=Job.attempts + 1)
        .returning(Job)
    )
    job = claimed.scalar_one_or_none()
    await session.commit()
    return job


async def complete_job(session: AsyncSession, job: Job) -> None:
    await session.execute(
        update(Job).where(Job.id == job.id).values(status=JobStatus.DONE, last_error=None)
    )
    await session.commit()


async def fail_job(session: AsyncSession, job: Job, error: str) -> None:
    await session.execute(
        update(Job).where(Job.id == job.id).values(status=JobStatus.FAILED, last_error=error[:4000])
    )
    await session.commit()
