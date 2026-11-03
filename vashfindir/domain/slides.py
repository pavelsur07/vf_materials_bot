from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import SlideGeneration

SLIDE_WIDTH = 1122
SLIDE_HEIGHT = 1402
SLIDE_ASPECT_RATIO = "561:701"
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
            raise ValueError("MVP slide output must be 1122x1402")
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
            raise ValueError("MVP slide aspect ratio must be 561:701")
        return self


class SlidePromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject_placeholder: str = Field(default="{plot}", min_length=1)
    style: str = Field(
        default=(
            "business editorial 2D cartoon illustration with clean vector-like shapes, "
            "crisp dark navy character outlines and soft tonal shading. "
            "When people are present, use slightly enlarged heads, simplified anatomy, "
            "expressive poses, near-white faces, small dark oval eyes and simple lines "
            "for the nose and mouth. Hair and clothing form clear dark navy silhouettes. "
            "Objects have simplified geometric forms; background objects use lighter, "
            "weaker outlines or adjacent color planes. Use soft diffuse daylight, "
            "gentle cool gray-blue shadows and smooth mostly matte surfaces. "
            "Small stylized highlights on glass and metal are allowed. "
            "Render the entire scene as a drawn 2D illustration, including faces and hands"
        ),
        min_length=1,
    )
    composition: str = Field(
        default=(
            "portrait orientation with a clear focal point and large readable foreground "
            "silhouettes. Keep the background predominantly near-white and pale cool "
            "gray-blue. Supporting objects explain the requested scene. Build moderate "
            "depth through overlap, scale and simple perspective; distant objects are "
            "lighter and less detailed. Leave light negative space between object groups. "
            "Choose people, objects and actions only from the requested subject"
        ),
        min_length=1,
    )
    palette: str = Field(
        default=(
            "predominantly near-white #F6F8FC and pale cool gray-blue #DDE3ED, "
            "with muted steel gray-blue #AEB9CA for secondary planes. "
            "Deep blue-black #162338 is reserved for character outlines, hair, clothing "
            "and selected foreground objects. Saturated red #C9002B provides small local "
            "accents on meaningful objects. The overall image stays light and cool; "
            "other saturated colors appear only when explicitly required by the subject"
        ),
        min_length=1,
    )
    detail_level: str = Field(
        default=(
            "moderate stylized detail on the main subject, simplified secondary objects "
            "and low-detail distant planes. Smooth fills and subtle gradients; "
            "no realistic skin pores, fabric weave, photographic texture or fine visual noise. "
            "If the subject includes an app or screen, draw a simple schematic interface "
            "with large shapes and icons, without readable text"
        ),
        min_length=1,
    )

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
            raise ValueError("MVP slide postprocessing target must be 1122x1402")
        return self


class SlideStyle(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: SlideStyleId = SlideStyleId.STYLE_01
    name: str = Field(default="Стиль 1", min_length=1)
    version: int = Field(default=2, ge=1)
    enabled: bool = True
    description: str = Field(
        default=(
            "Light cool-toned business 2D illustration based on foto-1.png and foto-4.png: "
            "dark navy contours, simplified pale faces and local red accents."
        ),
        min_length=1,
    )
    output: SlideOutputSpec = Field(default_factory=SlideOutputSpec)
    generation: SlideGenerationSettings = Field(default_factory=SlideGenerationSettings)
    prompt_template: SlidePromptTemplate = Field(default_factory=SlidePromptTemplate)
    negative_prompt: str = Field(
        default=(
            "photorealism, photography, realistic 3D render, realistic skin texture, "
            "cinematic lighting, dark background, warm ivory background, gold accents, "
            "glossy plastic, heavy black shadows, harsh directional lighting, "
            "painterly brush strokes, grain, noise, thick black outlines on every object, "
            "text, letters, words, typography, watermark, logo, signature, "
            "cropped main subject, blurry, low quality"
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
    await session.flush()
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


async def fail_interrupted_slide_generations(session: AsyncSession) -> int:
    result = await session.scalars(
        update(SlideGeneration)
        .where(SlideGeneration.status == SlideGenerationStatus.GENERATING)
        .values(
            status=SlideGenerationStatus.FAILED,
            error="worker restarted before slide generation completed",
            finished_at=_utcnow(),
        )
        .returning(SlideGeneration.id)
    )
    return len(result.all())
