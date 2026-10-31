from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse, RedirectResponse, Response

from vashfindir.apps.admin.auth import SESSION_USER_KEY, issue_csrf_token, verify_csrf
from vashfindir.apps.admin.deps import get_session, get_templates
from vashfindir.domain.slides import (
    SlideGenerationStatus,
    get_result_slide_path,
    get_slide_generation,
    list_slide_generations,
)
from vashfindir.modules.slides.dialogs import (
    GENERATION_ALREADY_RUNNING_MESSAGE,
    INVALID_PLOT_MESSAGE,
    SLIDE_STATUS_DESCRIPTIONS,
    SLIDE_STATUS_LABELS,
    SLIDES_DISABLED_MESSAGE,
    generation_queued_message,
)
from vashfindir.modules.slides.dto import SlideGenerationRequest
from vashfindir.modules.slides.use_cases import QueueSlideGenerationUseCase

router = APIRouter(prefix="/admin/slides")

_ACTIVE_STATUSES = {SlideGenerationStatus.QUEUED, SlideGenerationStatus.GENERATING}


def _slide_generation_use_case(request: Request) -> QueueSlideGenerationUseCase | None:
    return cast(
        QueueSlideGenerationUseCase | None,
        request.app.state.slide_generation_use_case,
    )


def _current_author(request: Request) -> str | None:
    author = request.session.get(SESSION_USER_KEY)
    return str(author) if author is not None else None


def _optional_positive_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


@router.get("")
async def slides_page(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    created_id = _optional_positive_id(request.query_params.get("created"))
    return get_templates(request).TemplateResponse(
        request,
        "slides.html",
        {
            "csrf_token": issue_csrf_token(request),
            "generations": await list_slide_generations(session, limit=50),
            "status_labels": SLIDE_STATUS_LABELS,
            "slide_generation_enabled": _slide_generation_use_case(request) is not None,
            "created_message": (
                generation_queued_message(created_id) if created_id is not None else None
            ),
            "invalid_plot": request.query_params.get("invalid_plot") == "1",
            "invalid_plot_message": INVALID_PLOT_MESSAGE,
            "disabled_message": SLIDES_DISABLED_MESSAGE,
        },
    )


@router.post("")
async def create_slide_generation(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await verify_csrf(request)
    use_case = _slide_generation_use_case(request)
    if use_case is None:
        return RedirectResponse(url="/admin/slides?disabled=1", status_code=303)

    form = await request.form()
    try:
        data = SlideGenerationRequest(plot=str(form.get("plot", "")))
    except ValidationError:
        return RedirectResponse(url="/admin/slides?invalid_plot=1", status_code=303)

    generation = await use_case.execute(
        session,
        data,
        author=_current_author(request),
    )
    return RedirectResponse(url=f"/admin/slides/{generation.id}?created=1", status_code=303)


@router.get("/{generation_id}")
async def slide_generation_page(
    generation_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    generation = await get_slide_generation(session, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Slide generation not found")

    created_id = _optional_positive_id(request.query_params.get("created"))
    return get_templates(request).TemplateResponse(
        request,
        "slide_detail.html",
        {
            "csrf_token": issue_csrf_token(request),
            "generation": generation,
            "status_labels": SLIDE_STATUS_LABELS,
            "status_descriptions": SLIDE_STATUS_DESCRIPTIONS,
            "generation_is_active": generation.status in _ACTIVE_STATUSES,
            "slide_generation_enabled": _slide_generation_use_case(request) is not None,
            "created_message": (
                generation_queued_message(created_id) if created_id is not None else None
            ),
            "invalid_plot": request.query_params.get("invalid_plot") == "1",
            "invalid_plot_message": INVALID_PLOT_MESSAGE,
            "already_running": request.query_params.get("already_running") == "1",
            "already_running_message": GENERATION_ALREADY_RUNNING_MESSAGE,
            "disabled_message": SLIDES_DISABLED_MESSAGE,
        },
    )


@router.post("/{generation_id}/retry")
async def retry_slide_generation(
    generation_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await verify_csrf(request)
    use_case = _slide_generation_use_case(request)
    if use_case is None:
        return RedirectResponse(url="/admin/slides?disabled=1", status_code=303)

    generation = await get_slide_generation(session, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Slide generation not found")
    if generation.status in _ACTIVE_STATUSES:
        return RedirectResponse(
            url=f"/admin/slides/{generation.id}?already_running=1",
            status_code=303,
        )

    try:
        data = SlideGenerationRequest(plot=generation.plot)
    except ValidationError:
        return RedirectResponse(
            url=f"/admin/slides/{generation.id}?invalid_plot=1",
            status_code=303,
        )

    new_generation = await use_case.execute(session, data, author=_current_author(request))
    return RedirectResponse(url=f"/admin/slides/{new_generation.id}?created=1", status_code=303)


@router.get("/{generation_id}/download")
async def download_slide_generation(
    generation_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    generation = await get_slide_generation(session, generation_id)
    expected_path = get_result_slide_path(generation_id)
    if (
        generation is None
        or generation.status != SlideGenerationStatus.READY
        or generation.image_path != str(expected_path)
        or not expected_path.is_file()
    ):
        raise HTTPException(status_code=404, detail="Slide image not found")

    return FileResponse(
        expected_path,
        media_type="image/png",
        filename=f"slide-{generation_id}.png",
    )
