import asyncio
from io import BytesIO
from typing import Annotated
from zoneinfo import ZoneInfo

# qrcode 8.x ships without a PEP 561 marker.
import qrcode  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import verify_csrf
from vashfindir.apps.admin.routes.attribution.access import (
    PREFIX,
    Actor,
    Database,
    bot_username,
    config,
    form_data,
    query_filters,
    render,
)
from vashfindir.db.models import AttributionLink, LeadMagnet
from vashfindir.domain.attribution.catalog import (
    CatalogError,
    DuplicateLink,
    create_link,
    update_link,
)
from vashfindir.domain.attribution.dto import LinkChanges, LinkInput
from vashfindir.domain.attribution.queries import (
    PAGE_SIZE,
    LinkFilter,
    link_choices,
    list_dict,
    list_filter_magnets,
    list_links,
)
from vashfindir.domain.attribution.settings import get_preferences

router = APIRouter()


@router.get("/links")
async def links_page(
    request: Request,
    session: Database,
    _: Actor,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
) -> Response:
    filters = query_filters(request, LinkFilter)
    prefs = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    rows = await list_links(session, filters, ZoneInfo(prefs.timezone), page)
    return render(
        request,
        "links",
        rows=rows[:PAGE_SIZE],
        filters=filters,
        page=page,
        next_page=len(rows) > PAGE_SIZE,
        magnets=await list_filter_magnets(session),
        sources=await list_dict(session, "source"),
        mediums=await list_dict(session, "medium"),
    )


async def link_form(
    request: Request,
    session: Database,
    values: object,
    *,
    status_code: int = 200,
    error: str | None = None,
    duplicate: str | None = None,
) -> Response:
    magnets, sources, mediums, recent = await link_choices(session)
    return render(
        request,
        "link_form",
        values=values,
        magnets=magnets,
        sources=sources,
        mediums=mediums,
        recent=recent,
        status_code=status_code,
        error=error,
        duplicate=duplicate,
    )


@router.get("/links/new")
async def new_link(
    request: Request,
    session: Database,
    _: Actor,
    copy: int | None = None,
) -> Response:
    values: object = await session.get(AttributionLink, copy) if copy is not None else {}
    if values is None:
        raise HTTPException(404)
    return await link_form(request, session, values)


@router.post("/links/new")
async def save_link(request: Request, session: Database, actor: Actor) -> Response:
    await verify_csrf(request)
    data = await form_data(request)
    confirmed = (await request.form()).get("confirm_duplicate") == "on"
    try:
        values = LinkInput.model_validate(data)
        link = await create_link(session, values, actor=actor, confirm_duplicate=confirmed)
    except DuplicateLink as exc:
        await session.rollback()
        return await link_form(
            request,
            session,
            data,
            status_code=409,
            duplicate=exc.code,
            error=str(exc),
        )
    except (CatalogError, ValidationError) as exc:
        await session.rollback()
        error = (
            str(exc)
            if isinstance(exc, CatalogError)
            else (
                "Заполните место, источник и канал. "
                "В UTM используйте латиницу, цифры и подчёркивания."
            )
        )
        return await link_form(request, session, data, status_code=422, error=error)
    await session.commit()
    return RedirectResponse(f"{PREFIX}/links/{link.id}", 303)


async def get_link(session: Database, link_id: int) -> AttributionLink:
    link = await session.get(AttributionLink, link_id)
    if link is None:
        raise HTTPException(404)
    return link


async def link_detail(
    request: Request,
    session: Database,
    link: AttributionLink,
    *,
    status_code: int = 200,
    error: str | None = None,
) -> Response:
    magnet = await session.get(LeadMagnet, link.lead_magnet_id)
    username = await bot_username(request)
    url = f"https://t.me/{username}?start={link.code}" if username else None
    return render(
        request,
        "link_detail",
        link=link,
        magnet=magnet,
        url=url,
        status_code=status_code,
        error=error,
    )


@router.get("/links/{link_id}")
async def view_link(request: Request, session: Database, _: Actor, link_id: int) -> Response:
    return await link_detail(request, session, await get_link(session, link_id))


@router.post("/links/{link_id}")
async def edit_link(request: Request, session: Database, actor: Actor, link_id: int) -> Response:
    await verify_csrf(request)
    link = await get_link(session, link_id)
    try:
        values = LinkChanges.model_validate(await form_data(request))
    except ValidationError:
        return await link_detail(
            request,
            session,
            link,
            status_code=422,
            error="Проверьте место, даты, бюджет и статус. Код, магнит и метки неизменяемы.",
        )
    await update_link(session, link, values, actor=actor)
    await session.commit()
    return RedirectResponse(f"{PREFIX}/links/{link_id}", 303)


def _generate_qr(url: str) -> bytes:
    result = BytesIO()
    qrcode.make(url).save(result, format="PNG")
    return result.getvalue()


@router.get("/links/{link_id}/qr.png")
async def link_qr(request: Request, session: Database, _: Actor, link_id: int) -> Response:
    link = await get_link(session, link_id)
    username = await bot_username(request)
    if not username:
        raise HTTPException(409, detail="Имя пользователя бота пока неизвестно.")
    png = await asyncio.to_thread(_generate_qr, f"https://t.me/{username}?start={link.code}")
    return Response(png, media_type="image/png")
