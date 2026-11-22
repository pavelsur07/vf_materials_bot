from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from vashfindir.apps.admin.routes.attribution.access import (
    Actor,
    Database,
    config,
    query_filters,
    render,
)
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
    )


@router.get("/exports")
async def exports_page(request: Request, _: Actor) -> Response:
    return render(request, "exports", exports_available=False)
