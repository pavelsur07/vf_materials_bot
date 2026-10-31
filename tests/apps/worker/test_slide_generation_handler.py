from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

import vashfindir.domain.slides as slides_domain
from vashfindir.apps.worker.handlers import GENERATE_SLIDE_JOB_TYPE, build_handlers
from vashfindir.db.models import SlideGeneration
from vashfindir.domain.jobs import enqueue_job
from vashfindir.domain.slides import SlideGenerationStatus, SlideStyleId, create_slide_generation
from vashfindir.integrations.image_generator import GeneratedImage, ImageGenerationError


class FakeImageGenerator:
    def __init__(
        self,
        content: bytes,
        *,
        provider_request_id: str = "provider-request-1",
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.provider_request_id = provider_request_id
        self.error = error
        self.requests: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        self.requests.append(
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "model": model,
                "width": width,
                "height": height,
            }
        )
        if self.error is not None:
            raise self.error
        return GeneratedImage(content=self.content, provider_request_id=self.provider_request_id)


def _png_bytes(size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "navy").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def generation_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "generated" / "slides"
    monkeypatch.setattr(slides_domain, "GENERATED_SLIDES_ROOT", root)
    return root


async def _create_generation(session: AsyncSession) -> SlideGeneration:
    return await create_slide_generation(
        session,
        plot="Финансовый директор анализирует падение выручки компании",
        style_id=SlideStyleId.STYLE_01,
        style_version=1,
        model="mock-model",
        prompt="Visual subject: тест",
        negative_prompt="text, watermark",
        author="admin",
    )


async def test_handler_generates_normalizes_and_saves_slide(
    session: AsyncSession,
    generation_root: Path,
) -> None:
    generation = await _create_generation(session)
    job = await enqueue_job(
        session,
        GENERATE_SLIDE_JOB_TYPE,
        {"slide_generation_id": generation.id},
    )
    original_content = _png_bytes((1600, 900))
    image_generator = FakeImageGenerator(original_content)

    await build_handlers(image_generator)[GENERATE_SLIDE_JOB_TYPE](job, session)

    original_path = generation_root / str(generation.id) / "original.png"
    result_path = generation_root / str(generation.id) / "slide.png"
    assert generation.status == SlideGenerationStatus.READY
    assert generation.provider_request_id == "provider-request-1"
    assert generation.original_path == str(original_path)
    assert generation.image_path == str(result_path)
    assert generation.started_at is not None
    assert generation.finished_at is not None
    assert original_path.read_bytes() == original_content

    with Image.open(result_path) as image:
        assert image.format == "PNG"
        assert image.size == (1080, 1350)

    assert image_generator.requests == [
        {
            "prompt": "Visual subject: тест",
            "negative_prompt": "text, watermark",
            "model": "mock-model",
            "width": 1080,
            "height": 1350,
        }
    ]


async def test_handler_marks_generation_failed_for_invalid_image(
    session: AsyncSession,
    generation_root: Path,
) -> None:
    generation = await _create_generation(session)
    job = await enqueue_job(
        session,
        GENERATE_SLIDE_JOB_TYPE,
        {"slide_generation_id": generation.id},
    )

    with pytest.raises(RuntimeError, match="slide generation failed"):
        await build_handlers(FakeImageGenerator(b"not an image"))[GENERATE_SLIDE_JOB_TYPE](
            job, session
        )

    assert generation.status == SlideGenerationStatus.FAILED
    assert generation.error is not None
    assert "valid PNG" in generation.error
    assert not (generation_root / str(generation.id) / "slide.png").exists()


async def test_handler_marks_generation_failed_when_provider_raises(
    session: AsyncSession,
    generation_root: Path,
) -> None:
    generation = await _create_generation(session)
    job = await enqueue_job(
        session,
        GENERATE_SLIDE_JOB_TYPE,
        {"slide_generation_id": generation.id},
    )

    with pytest.raises(RuntimeError, match="provider timeout"):
        await build_handlers(
            FakeImageGenerator(b"", error=ImageGenerationError("provider timeout"))
        )[GENERATE_SLIDE_JOB_TYPE](job, session)

    assert generation.status == SlideGenerationStatus.FAILED
    assert generation.error is not None
    assert "provider timeout" in generation.error
    assert not (generation_root / str(generation.id) / "slide.png").exists()


async def test_handler_rejects_invalid_payload(session: AsyncSession) -> None:
    job = await enqueue_job(
        session,
        GENERATE_SLIDE_JOB_TYPE,
        {"slide_generation_id": "not-an-integer"},
    )

    with pytest.raises(ValueError, match="positive slide_generation_id"):
        await build_handlers(FakeImageGenerator(_png_bytes((100, 100))))[GENERATE_SLIDE_JOB_TYPE](
            job, session
        )


async def test_handler_rejects_missing_generation(session: AsyncSession) -> None:
    job = await enqueue_job(
        session,
        GENERATE_SLIDE_JOB_TYPE,
        {"slide_generation_id": 999},
    )

    with pytest.raises(ValueError, match="does not exist"):
        await build_handlers(FakeImageGenerator(_png_bytes((100, 100))))[GENERATE_SLIDE_JOB_TYPE](
            job, session
        )
