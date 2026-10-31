import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import Job
from vashfindir.domain.jobs import enqueue_job, utcnow
from vashfindir.domain.slide_images import normalize_slide_png
from vashfindir.domain.slides import (
    GENERATE_SLIDE_JOB_TYPE,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    get_original_slide_path,
    get_result_slide_path,
    get_slide_generation,
    mark_slide_generation_failed,
    mark_slide_generation_generating,
    mark_slide_generation_ready,
)
from vashfindir.domain.stats import count_users
from vashfindir.integrations.image_generator import ImageGenerator
from vashfindir.integrations.mock_image_generator import MockImageGenerator

logger = logging.getLogger(__name__)

DAILY_STATS = "daily_stats"
DAILY_STATS_INTERVAL = timedelta(days=1)

Handler = Callable[[Job, AsyncSession], Awaitable[None]]


async def _daily_stats(job: Job, session: AsyncSession) -> None:
    total = await count_users(session)
    logger.info("daily_stats: users=%s", total)
    # Сама задача ставит следующий запуск: текущая в статусе running,
    # поэтому ensure_scheduled здесь не подошёл бы.
    await enqueue_job(session, DAILY_STATS, run_at=utcnow() + DAILY_STATS_INTERVAL)


def _slide_generation_id(job: Job) -> int:
    try:
        payload = json.loads(job.payload or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("slide job payload must be valid JSON") from exc
    generation_id = payload.get("slide_generation_id")
    if isinstance(generation_id, bool) or not isinstance(generation_id, int) or generation_id < 1:
        raise ValueError("slide job payload must contain a positive slide_generation_id")
    return generation_id


def _save_slide_files(
    original_path: Path,
    result_path: Path,
    original_content: bytes,
    result_content: bytes,
) -> None:
    original_path.parent.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(original_content)
    result_path.write_bytes(result_content)


async def _generate_slide(
    job: Job,
    session: AsyncSession,
    image_generator: ImageGenerator,
) -> None:
    generation_id = _slide_generation_id(job)
    generation = await get_slide_generation(session, generation_id)
    if generation is None:
        raise ValueError(f"slide generation {generation_id} does not exist")

    await mark_slide_generation_generating(session, generation)
    try:
        generated = await image_generator.generate(
            prompt=generation.prompt,
            negative_prompt=generation.negative_prompt,
            model=generation.model,
            width=SLIDE_WIDTH,
            height=SLIDE_HEIGHT,
        )
        normalized = await normalize_slide_png(generated.content)
        original_path = get_original_slide_path(generation.id)
        result_path = get_result_slide_path(generation.id)
        await asyncio.to_thread(
            _save_slide_files,
            original_path,
            result_path,
            generated.content,
            normalized,
        )
        await mark_slide_generation_ready(
            session,
            generation,
            image_path=str(result_path),
            original_path=str(original_path),
            provider_request_id=generated.provider_request_id,
        )
    except Exception as exc:
        error = f"slide generation failed: {exc}"
        await mark_slide_generation_failed(session, generation, error)
        raise RuntimeError(error) from exc


def build_handlers(image_generator: ImageGenerator) -> dict[str, Handler]:
    async def generate_slide(job: Job, session: AsyncSession) -> None:
        await _generate_slide(job, session, image_generator)

    return {DAILY_STATS: _daily_stats, GENERATE_SLIDE_JOB_TYPE: generate_slide}


HANDLERS = build_handlers(MockImageGenerator())
