from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.apps.worker.handlers import (
    DAILY_STATS,
    DAILY_STATS_INTERVAL,
    HANDLERS,
    recover_interrupted_work,
)
from vashfindir.db.models import Job, User
from vashfindir.domain.jobs import JobStatus, claim_due_job, enqueue_job, utcnow
from vashfindir.domain.slides import (
    SlideGenerationStatus,
    SlideStyleId,
    create_slide_generation,
    mark_slide_generation_generating,
)


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


async def test_recovery_marks_interrupted_work_failed(session: AsyncSession) -> None:
    generation = await create_slide_generation(
        session,
        plot="Сюжет для тестовой генерации",
        style_id=SlideStyleId.STYLE_01,
        style_version=1,
        model="mock-model",
        prompt="Visual subject: test",
        negative_prompt="text, watermark",
    )
    await mark_slide_generation_generating(session, generation)
    await enqueue_job(session, DAILY_STATS)
    running = await claim_due_job(session)
    assert running is not None
    pending = await enqueue_job(session, "pending")
    await session.commit()

    await recover_interrupted_work(session)
    await session.refresh(generation)

    assert running.status == JobStatus.FAILED
    assert running.last_error == "worker restarted before job completion"
    assert generation.status == SlideGenerationStatus.FAILED
    assert generation.error == "worker restarted before slide generation completed"
    assert generation.finished_at is not None
    assert pending.status == JobStatus.PENDING
