from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.core.exceptions import UseCaseError
from vashfindir.db.models import SlideGeneration
from vashfindir.domain.jobs import enqueue_job
from vashfindir.domain.slides import GENERATE_SLIDE_JOB_TYPE, SlideStyle, create_slide_generation
from vashfindir.modules.slides.dto import SlideGenerationRequest, SlideGenerationResult


class PrepareSlideGenerationUseCase:
    """Prepare one slide generation without touching the database or an external API."""

    def __init__(self, style: SlideStyle) -> None:
        self._style = style

    def execute(self, request: SlideGenerationRequest) -> SlideGenerationResult:
        if not self._style.enabled:
            raise UseCaseError("slide style is disabled")
        if self._style.id != request.style_id:
            raise UseCaseError("slide style is not available")

        return SlideGenerationResult(
            plot=request.plot,
            style_id=self._style.id,
            style_version=self._style.version,
            model=self._style.generation.model,
            prompt=self._style.build_prompt(request.plot),
            negative_prompt=self._style.negative_prompt,
            image_format=self._style.output.format,
            width=self._style.output.width,
            height=self._style.output.height,
        )


class QueueSlideGenerationUseCase:
    """Create a slide generation record and enqueue its background processing."""

    def __init__(self, style: SlideStyle, *, generation_model: str | None = None) -> None:
        self._style = style
        self._generation_model = generation_model or None
        self._prepare = PrepareSlideGenerationUseCase(style)

    async def execute(
        self,
        session: AsyncSession,
        request: SlideGenerationRequest,
        *,
        author: str | None = None,
    ) -> SlideGeneration:
        prepared = self._prepare.execute(request)
        try:
            generation = await create_slide_generation(
                session,
                plot=prepared.plot,
                style_id=prepared.style_id,
                style_version=prepared.style_version,
                model=self._generation_model or prepared.model,
                prompt=prepared.prompt,
                negative_prompt=prepared.negative_prompt,
                author=author,
            )
            await enqueue_job(
                session,
                GENERATE_SLIDE_JOB_TYPE,
                {"slide_generation_id": generation.id},
            )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise UseCaseError("failed to queue slide generation") from exc
        return generation
