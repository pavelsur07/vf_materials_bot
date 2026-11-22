from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import verify_csrf
from vashfindir.apps.admin.routes.attribution.access import (
    PREFIX,
    Actor,
    Database,
    delivery_adapter,
    form_data,
    render,
)
from vashfindir.db.models import DictValue, LeadMagnet
from vashfindir.domain.attribution.catalog import save_dict_value, save_magnet
from vashfindir.domain.attribution.dto import (
    DictValueInput,
    MagnetContent,
    MagnetInput,
    NewMagnetInput,
)
from vashfindir.domain.attribution.queries import list_dict, list_magnets

router = APIRouter()


@router.get("/magnets")
async def magnets_page(request: Request, session: Database, _: Actor) -> Response:
    rows = await list_magnets(session)
    return render(request, "magnets", rows=rows, sent=request.query_params.get("sent"))


@router.get("/magnets/new")
async def new_magnet(request: Request, _: Actor) -> Response:
    return render(request, "magnet_form", entry=None, values={"is_active": True, "sort": 0})


@router.get("/magnets/{magnet_id:int}")
async def edit_magnet(request: Request, session: Database, _: Actor, magnet_id: int) -> Response:
    magnet = await session.get(LeadMagnet, magnet_id)
    if magnet is None:
        raise HTTPException(404)
    return render(request, "magnet_form", entry=magnet, values=magnet)


@router.post("/magnets/new")
@router.post("/magnets/{magnet_id:int}")
async def change_magnet(
    request: Request,
    session: Database,
    actor: Actor,
    magnet_id: int | None = None,
) -> Response:
    await verify_csrf(request)
    magnet = await session.get(LeadMagnet, magnet_id) if magnet_id is not None else None
    if magnet is None and magnet_id is not None:
        raise HTTPException(404)
    data: dict[str, object] = dict(await form_data(request))
    data["is_active"] = data.get("is_active") == "on"
    data["message"] = data.get("message") or ""
    try:
        values = (MagnetInput if magnet else NewMagnetInput).model_validate(data)
        await save_magnet(session, values, actor=actor, magnet=magnet)
        await session.commit()
    except (ValidationError, IntegrityError) as exc:
        if isinstance(exc, IntegrityError):
            await session.rollback()
        return render(
            request,
            "magnet_form",
            entry=magnet,
            values=data,
            status_code=422,
            error="Проверьте тип и содержимое. Префикс должен быть уникальным и состоять "
            "из 2–10 строчных латинских букв или цифр.",
        )
    return RedirectResponse(f"{PREFIX}/magnets", 303)


@router.post("/magnets/{magnet_id:int}/preview")
async def preview(request: Request, session: Database, actor: Actor, magnet_id: int) -> Response:
    await verify_csrf(request)
    entry = await session.get(LeadMagnet, magnet_id)
    if entry is None:
        raise HTTPException(404)
    adapter = delivery_adapter(request)
    content = MagnetContent.model_validate(entry)
    await session.rollback()
    sent = await adapter.send_magnet(actor, content) if adapter else None
    outcome = "ok" if sent and sent.status == "sent" else "error"
    return RedirectResponse(f"{PREFIX}/magnets?sent={outcome}", 303)


@router.get("/dictionaries")
async def dictionaries(
    request: Request,
    session: Database,
    _: Actor,
    kind: Literal["source", "medium"] = "source",
) -> Response:
    entries = await list_dict(session, kind)
    return render(
        request,
        "dictionaries",
        entries=entries,
        kind=kind,
        error="Проверьте уникальность метки. Допустимы латинские буквы, цифры и подчёркивания."
        if request.query_params.get("error") == "1"
        else None,
    )


@router.post("/dictionaries/{kind}")
@router.post("/dictionaries/{kind}/{entry_id}")
async def change_dictionary(
    request: Request,
    session: Database,
    actor: Actor,
    kind: Literal["source", "medium"],
    entry_id: int | None = None,
) -> Response:
    await verify_csrf(request)
    entry = await session.get(DictValue, entry_id) if entry_id is not None else None
    if entry_id is not None and (entry is None or entry.dict != kind):
        raise HTTPException(404)
    data: dict[str, object] = dict(await form_data(request))
    data["is_active"] = data.get("is_active") == "on"
    if entry:
        data["value"] = entry.value
    try:
        values = DictValueInput.model_validate(data)
        await save_dict_value(session, kind, values, actor=actor, entry=entry)
        await session.commit()
    except (ValidationError, IntegrityError):
        await session.rollback()
        return RedirectResponse(f"{PREFIX}/dictionaries?kind={kind}&error=1", 303)
    return RedirectResponse(f"{PREFIX}/dictionaries?kind={kind}", 303)
