from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import verify_csrf
from vashfindir.apps.admin.routes.attribution.access import (
    PREFIX,
    Actor,
    Database,
    config,
    query_filters,
    render,
)
from vashfindir.domain.attribution.bitrix_queue import retry_errors
from vashfindir.domain.attribution.queries import (
    PAGE_SIZE,
    TouchFilter,
    list_filter_magnets,
    list_touches,
)
from vashfindir.domain.attribution.settings import get_preferences

router = APIRouter()


@router.get("/touches")
async def touches_page(
    request: Request,
    session: Database,
    _: Actor,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
) -> Response:
    filters = query_filters(request, TouchFilter)
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    rows = await list_touches(session, filters, ZoneInfo(prefs.timezone), page)
    return render(
        request,
        "touches",
        rows=rows[:PAGE_SIZE],
        filters=filters,
        page=page,
        next_page=len(rows) > PAGE_SIZE,
        magnets=await list_filter_magnets(session),
        retry_available=True,
        retry_count=request.query_params.get("retried"),
    )


@router.post("/touches/retry")
@router.post("/touches/{touch_id:int}/retry")
async def retry(
    request: Request,
    session: Database,
    _: Actor,
    touch_id: int | None = None,
) -> Response:
    await verify_csrf(request)
    count = await retry_errors(session, touch_id)
    await session.commit()
    return RedirectResponse(f"{PREFIX}/touches?retried={count}", 303)
