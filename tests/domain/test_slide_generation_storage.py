from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import SlideGeneration
from vashfindir.domain.slides import (
    GENERATED_SLIDES_ROOT,
    SlideGenerationStatus,
    SlideStyleId,
    create_slide_generation,
    get_original_slide_path,
    get_result_slide_path,
    get_slide_generation,
    get_slide_generation_dir,
    list_slide_generations,
    mark_slide_generation_failed,
    mark_slide_generation_generating,
    mark_slide_generation_ready,
)


async def _create_generation(
    session: AsyncSession,
    plot: str = "Сюжет для тестовой генерации",
) -> SlideGeneration:
    return await create_slide_generation(
        session,
        plot=plot,
        style_id=SlideStyleId.STYLE_01,
        style_version=1,
        model="mock-model",
        prompt="Visual subject: test",
        negative_prompt="text, watermark",
        author="admin",
    )


async def test_create_slide_generation_stores_request_metadata(session: AsyncSession) -> None:
    generation = await _create_generation(session)

    assert generation.id is not None
    assert generation.plot == "Сюжет для тестовой генерации"
    assert generation.style_id == "style_01"
    assert generation.style_version == 1
    assert generation.model == "mock-model"
    assert generation.prompt == "Visual subject: test"
    assert generation.negative_prompt == "text, watermark"
    assert generation.author == "admin"
    assert generation.status == SlideGenerationStatus.QUEUED
    assert generation.created_at is not None


async def test_get_and_list_slide_generations(session: AsyncSession) -> None:
    first = await _create_generation(session, plot="Первый сюжет")
    second = await _create_generation(session, plot="Второй сюжет")

    loaded = await get_slide_generation(session, first.id)
    generations = await list_slide_generations(session)

    assert loaded is not None
    assert loaded.id == first.id
    assert [item.id for item in generations] == [second.id, first.id]


async def test_mark_generating_and_ready(session: AsyncSession) -> None:
    generation = await _create_generation(session)

    await mark_slide_generation_generating(session, generation)
    assert generation.status == SlideGenerationStatus.GENERATING
    assert generation.started_at is not None
    assert generation.error is None

    await mark_slide_generation_ready(
        session,
        generation,
        image_path="data/generated/slides/1/slide.png",
        original_path="data/generated/slides/1/original.png",
        provider_request_id="provider-1",
    )

    assert generation.status == SlideGenerationStatus.READY
    assert generation.image_path == "data/generated/slides/1/slide.png"
    assert generation.original_path == "data/generated/slides/1/original.png"
    assert generation.provider_request_id == "provider-1"
    assert generation.finished_at is not None


async def test_mark_failed_stores_safe_error(session: AsyncSession) -> None:
    generation = await _create_generation(session)

    await mark_slide_generation_failed(session, generation, "provider timeout")

    assert generation.status == SlideGenerationStatus.FAILED
    assert generation.error == "provider timeout"
    assert generation.finished_at is not None


def test_slide_file_paths_are_derived_from_generation_id() -> None:
    assert Path("data/generated/slides") == GENERATED_SLIDES_ROOT
    assert get_slide_generation_dir(42) == Path("data/generated/slides/42")
    assert get_original_slide_path(42) == Path("data/generated/slides/42/original.png")
    assert get_result_slide_path(42) == Path("data/generated/slides/42/slide.png")


def test_slide_file_paths_reject_invalid_generation_id() -> None:
    with pytest.raises(ValueError, match="positive"):
        get_slide_generation_dir(0)
