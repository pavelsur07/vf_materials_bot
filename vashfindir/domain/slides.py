from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import SlideGeneration

SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350
SLIDE_ASPECT_RATIO = "4:5"
MIN_PLOT_LENGTH = 10
MAX_PLOT_LENGTH = 1000


class SlideImageFormat(StrEnum):
    PNG = "png"


class SlideStyleId(StrEnum):
    STYLE_01 = "style_01"


class SlideOutputSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: SlideImageFormat = SlideImageFormat.PNG
    width: int = Field(default=SLIDE_WIDTH, ge=1)
    height: int = Field(default=SLIDE_HEIGHT, ge=1)

    @model_validator(mode="after")
    def _fixed_mvp_size(self) -> Self:
        if self.width != SLIDE_WIDTH or self.height != SLIDE_HEIGHT:
            raise ValueError("MVP slide output must be 1080x1350")
        return self


class SlideGenerationSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(default="mock-model", min_length=1)
    aspect_ratio: str = Field(default=SLIDE_ASPECT_RATIO)
    seed: int | None = None
    quality: str = Field(default="high", min_length=1)

    @model_validator(mode="after")
    def _fixed_mvp_aspect_ratio(self) -> Self:
        if self.aspect_ratio != SLIDE_ASPECT_RATIO:
            raise ValueError("MVP slide aspect ratio must be 4:5")
        return self


class SlidePromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject_placeholder: str = Field(default="{plot}", min_length=1)
    style: str = Field(
        default=(
            "modern editorial illustration, clean composition, soft cinematic lighting, "
            "premium business visual, calm and trustworthy atmosphere"
        ),
        min_length=1,
    )
    composition: str = Field(
        default=(
            "centered subject with negative space around it, portrait orientation, "
            "no visible text areas"
        ),
        min_length=1,
    )
    palette: str = Field(
        default="deep navy blue, warm ivory, muted gold accents",
        min_length=1,
    )
    detail_level: str = Field(default="highly detailed but uncluttered", min_length=1)

    @model_validator(mode="after")
    def _single_plot_placeholder(self) -> Self:
        if self.subject_placeholder != "{plot}":
            raise ValueError("prompt template must contain the {plot} placeholder")
        return self

    def render(self, plot: str) -> str:
        sections = (
            ("Visual subject", plot),
            ("Style", self.style),
            ("Composition", self.composition),
            ("Palette", self.palette),
            ("Detail level", self.detail_level),
        )
        return "\n".join(f"{title}: {value}" for title, value in sections)


class SlidePostprocessingSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_width: int = Field(default=SLIDE_WIDTH, ge=1)
    target_height: int = Field(default=SLIDE_HEIGHT, ge=1)
    allow_crop: bool = True
    allow_resize: bool = True
    strip_metadata: bool = True

    @model_validator(mode="after")
    def _fixed_mvp_target(self) -> Self:
        if self.target_width != SLIDE_WIDTH or self.target_height != SLIDE_HEIGHT:
            raise ValueError("MVP slide postprocessing target must be 1080x1350")
        return self


class SlideStyle(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: SlideStyleId = SlideStyleId.STYLE_01
    name: str = Field(default="Style 01", min_length=1)
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    description: str = Field(
        default="Test visual style for the MVP slide generator.",
        min_length=1,
    )
    output: SlideOutputSpec = Field(default_factory=SlideOutputSpec)
    generation: SlideGenerationSettings = Field(default_factory=SlideGenerationSettings)
    prompt_template: SlidePromptTemplate = Field(default_factory=SlidePromptTemplate)
    negative_prompt: str = Field(
        default=(
            "text, letters, words, typography, watermark, logo, signature, UI elements, "
            "cropped subject, blurry, low quality, oversaturated, harsh shadows"
        ),
        min_length=1,
    )
    postprocessing: SlidePostprocessingSpec = Field(default_factory=SlidePostprocessingSpec)

    def build_prompt(self, plot: str) -> str:
        return self.prompt_template.render(plot)


def default_slide_style() -> SlideStyle:
    """Return the single style enabled by the MVP contract."""
    return SlideStyle()


class SlideGenerationStatus(StrEnum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


GENERATE_SLIDE_JOB_TYPE = "generate_slide"

GENERATED_SLIDES_ROOT = Path("data/generated/slides")


def get_slide_generation_dir(generation_id: int) -> Path:
    if generation_id < 1:
        raise ValueError("generation_id must be positive")
    return GENERATED_SLIDES_ROOT / str(generation_id)


def get_original_slide_path(generation_id: int) -> Path:
    return get_slide_generation_dir(generation_id) / "original.png"


def get_result_slide_path(generation_id: int) -> Path:
    return get_slide_generation_dir(generation_id) / "slide.png"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def create_slide_generation(
    session: AsyncSession,
    *,
    plot: str,
    style_id: SlideStyleId,
    style_version: int,
    model: str,
    prompt: str,
    negative_prompt: str,
    author: str | None = None,
) -> SlideGeneration:
    generation = SlideGeneration(
        plot=plot,
        style_id=str(style_id),
        style_version=style_version,
        model=model,
        prompt=prompt,
        negative_prompt=negative_prompt,
        author=author,
        status=SlideGenerationStatus.QUEUED,
    )
    session.add(generation)
    await session.commit()
    return generation


async def get_slide_generation(
    session: AsyncSession,
    generation_id: int,
) -> SlideGeneration | None:
    return await session.get(SlideGeneration, generation_id)


async def list_slide_generations(
    session: AsyncSession,
    limit: int = 20,
) -> list[SlideGeneration]:
    result = await session.scalars(
        select(SlideGeneration).order_by(SlideGeneration.id.desc()).limit(limit)
    )
    return list(result)


async def mark_slide_generation_generating(
    session: AsyncSession,
    generation: SlideGeneration,
) -> None:
    generation.status = SlideGenerationStatus.GENERATING
    generation.started_at = _utcnow()
    generation.error = None
    await session.commit()


async def mark_slide_generation_ready(
    session: AsyncSession,
    generation: SlideGeneration,
    *,
    image_path: str,
    original_path: str | None = None,
    provider_request_id: str | None = None,
) -> None:
    generation.status = SlideGenerationStatus.READY
    generation.image_path = image_path
    generation.original_path = original_path
    generation.provider_request_id = provider_request_id
    generation.error = None
    generation.finished_at = _utcnow()
    await session.commit()


async def mark_slide_generation_failed(
    session: AsyncSession,
    generation: SlideGeneration,
    error: str,
) -> None:
    generation.status = SlideGenerationStatus.FAILED
    generation.error = error[:4000]
    generation.finished_at = _utcnow()
    await session.commit()
