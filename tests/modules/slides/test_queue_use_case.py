import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.core.exceptions import UseCaseError
from vashfindir.db.models import Job, SlideGeneration
from vashfindir.domain.jobs import JobStatus
from vashfindir.domain.slides import GENERATE_SLIDE_JOB_TYPE, default_slide_style
from vashfindir.modules.slides.dto import SlideGenerationRequest
from vashfindir.modules.slides.use_cases import QueueSlideGenerationUseCase


@pytest.fixture
def use_case() -> QueueSlideGenerationUseCase:
    return QueueSlideGenerationUseCase(default_slide_style())


async def test_creates_generation_and_enqueues_worker_job(
    session: AsyncSession,
    use_case: QueueSlideGenerationUseCase,
) -> None:
    request = SlideGenerationRequest(
        plot="Финансовый директор анализирует падение выручки компании"
    )

    generation = await use_case.execute(session, request, author="admin")

    assert generation.id is not None
    assert generation.status == "queued"
    assert generation.plot == request.plot
    assert generation.style_id == "style_01"
    assert generation.style_version == 1
    assert generation.author == "admin"
    assert "Visual subject:" in generation.prompt

    job = await session.scalar(select(Job).where(Job.type == GENERATE_SLIDE_JOB_TYPE))
    assert job is not None
    assert job.status == JobStatus.PENDING
    assert json.loads(job.payload) == {"slide_generation_id": generation.id}

    assert await session.scalar(select(func.count()).select_from(SlideGeneration)) == 1


async def test_rejects_request_without_creating_records(
    session: AsyncSession,
    use_case: QueueSlideGenerationUseCase,
) -> None:
    disabled_style = default_slide_style().model_copy(update={"enabled": False})
    disabled_use_case = QueueSlideGenerationUseCase(disabled_style)

    with pytest.raises(UseCaseError, match="disabled"):
        await disabled_use_case.execute(
            session,
            SlideGenerationRequest(plot="Сюжет для тестовой генерации"),
        )

    assert await session.scalar(select(func.count()).select_from(SlideGeneration)) == 0
    assert await session.scalar(select(func.count()).select_from(Job)) == 0


async def test_configured_provider_model_is_saved_instead_of_style_model(
    session: AsyncSession,
) -> None:
    use_case = QueueSlideGenerationUseCase(
        default_slide_style(),
        generation_model="gpt-image-2.5-flare",
    )

    generation = await use_case.execute(
        session,
        SlideGenerationRequest(plot="Сюжет для тестовой генерации"),
    )

    assert generation.model == "gpt-image-2.5-flare"


async def test_rolls_back_generation_when_job_enqueue_fails(
    session: AsyncSession,
    use_case: QueueSlideGenerationUseCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_enqueue(*args: object, **kwargs: object) -> None:
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(
        "vashfindir.modules.slides.use_cases.enqueue_job",
        fail_enqueue,
    )

    with pytest.raises(UseCaseError, match="failed to queue"):
        await use_case.execute(
            session,
            SlideGenerationRequest(plot="Сюжет для тестовой генерации"),
        )

    assert await session.scalar(select(func.count()).select_from(SlideGeneration)) == 0
    assert await session.scalar(select(func.count()).select_from(Job)) == 0
