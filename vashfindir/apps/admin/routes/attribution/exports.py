from collections.abc import AsyncIterator
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from starlette.responses import Response, StreamingResponse

from vashfindir.apps.admin.routes.attribution.access import (
    Actor,
    Database,
    config,
    query_filters,
    render,
)
from vashfindir.domain.attribution.exports import export_links, export_touches
from vashfindir.domain.attribution.queries import DateWindow
from vashfindir.domain.attribution.settings import get_preferences

router = APIRouter()


@router.get("/exports")
async def exports_page(request: Request, session: Database, _: Actor) -> Response:
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    return render(request, "exports", timezone=prefs.timezone)


def _download(rows: AsyncIterator[bytes], filename: str) -> StreamingResponse:
    return StreamingResponse(
        rows,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/exports/links.csv")
async def links_csv(request: Request, session: Database, _: Actor) -> StreamingResponse:
    period = query_filters(request, DateWindow)
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    return _download(export_links(session, period, ZoneInfo(prefs.timezone)), "links.csv")


@router.get("/exports/touches.csv")
async def touches_csv(
    request: Request,
    session: Database,
    _: Actor,
    include_test: bool = False,
) -> StreamingResponse:
    period = query_filters(request, DateWindow)
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    rows = export_touches(session, period, ZoneInfo(prefs.timezone), include_test=include_test)
    return _download(rows, "touches.csv")
