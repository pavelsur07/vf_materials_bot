import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Job
from bot.services.jobs import (
    JobStatus,
    claim_due_job,
    complete_job,
    enqueue_job,
    ensure_scheduled,
    fail_job,
    utcnow,
)


async def test_enqueue_and_claim(session: AsyncSession) -> None:
    job = await enqueue_job(session, "demo", {"a": 1})

    assert job.status == JobStatus.PENDING

    claimed = await claim_due_job(session)

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempts == 1
    assert json.loads(claimed.payload) == {"a": 1}
    # Повторный захват не отдаёт ту же задачу
    assert await claim_due_job(session) is None


async def test_claim_returns_none_when_queue_empty(session: AsyncSession) -> None:
    assert await claim_due_job(session) is None


async def test_claim_skips_not_yet_due_job(session: AsyncSession) -> None:
    await enqueue_job(session, "demo", run_at=utcnow() + timedelta(hours=1))

    assert await claim_due_job(session) is None


async def test_claim_oldest_first(session: AsyncSession) -> None:
    first = await enqueue_job(session, "demo")
    await enqueue_job(session, "demo")

    claimed = await claim_due_job(session)

    assert claimed is not None
    assert claimed.id == first.id


async def test_complete_job(session: AsyncSession) -> None:
    await enqueue_job(session, "demo")
    job = await claim_due_job(session)
    assert job is not None

    await complete_job(session, job)

    status = await session.scalar(select(Job.status).where(Job.id == job.id))
    assert status == JobStatus.DONE


async def test_fail_job_keeps_error(session: AsyncSession) -> None:
    await enqueue_job(session, "demo")
    job = await claim_due_job(session)
    assert job is not None

    await fail_job(session, job, "boom")

    reloaded = await session.get(Job, job.id)
    assert reloaded is not None
    assert reloaded.status == JobStatus.FAILED
    assert reloaded.last_error == "boom"


async def test_ensure_scheduled_enqueues_once(session: AsyncSession) -> None:
    job = await ensure_scheduled(session, "daily", timedelta(days=1))

    assert job is not None
    assert job.run_at > utcnow()
    assert await ensure_scheduled(session, "daily", timedelta(days=1)) is None
