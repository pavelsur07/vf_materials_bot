import re
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import CSRF_SESSION_KEY, issue_csrf_token, verify_csrf
from vashfindir.apps.admin.deps import get_session, get_templates
from vashfindir.core.config import Settings
from vashfindir.domain.attribution.admin_access import consume_challenge, issue_challenge
from vashfindir.domain.attribution.settings import get_preferences
from vashfindir.integrations.telegram_delivery import TelegramDelivery

PREFIX = "/admin/attribution"
SESSION_TG_ID = "attribution_tg_id"
SESSION_CHALLENGE = "attribution_challenge"
router = APIRouter()
Database = Annotated[AsyncSession, Depends(get_session)]
_WRITE_KEYS = {"csrf_token", "confirm_duplicate"}


def config(request: Request) -> Settings:
    settings = cast(Settings, request.app.state.settings)
    if not settings.attribution_enabled:
        raise HTTPException(404)
    return settings


async def actor_id(request: Request, session: Database) -> int:
    settings = config(request)
    actor = request.session.get(SESSION_TG_ID)
    preferences = await get_preferences(session, settings.attribution_bootstrap_admin_tg_ids)
    if not isinstance(actor, int) or actor not in preferences.admin_ids:
        request.session.pop(SESSION_TG_ID, None)
        raise HTTPException(303, headers={"Location": f"{PREFIX}/access"})
    return actor


Actor = Annotated[int, Depends(actor_id)]


def render(
    request: Request,
    template: str,
    *,
    status_code: int = 200,
    **values: object,
) -> Response:
    token = request.session.get(CSRF_SESSION_KEY) or issue_csrf_token(request)
    return get_templates(request).TemplateResponse(
        request,
        f"attribution/{template}.html",
        {"csrf_token": token, **values},
        status_code=status_code,
    )


async def form_data(request: Request) -> dict[str, str | None]:
    return {
        key: str(value) if value != "" else None
        for key, value in (await request.form()).items()
        if key not in _WRITE_KEYS
    }


def delivery_adapter(request: Request) -> TelegramDelivery | None:
    return cast(TelegramDelivery | None, request.app.state.attribution_delivery)


async def bot_username(request: Request) -> str | None:
    username = config(request).attribution_bot_username.strip().lstrip("@")
    if not username and (adapter := delivery_adapter(request)) is not None:
        username = await adapter.bot_username() or ""
    return username if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) else None


@router.get("/access")
async def access_page(request: Request, session: Database) -> Response:
    config(request)
    async with session.begin():
        code = await issue_challenge(session)
    request.session[SESSION_CHALLENGE] = code
    return render(request, "access", code=code)


@router.post("/access")
async def confirm_access(request: Request, session: Database) -> Response:
    settings = config(request)
    await verify_csrf(request)
    code = str(request.session.get(SESSION_CHALLENGE, ""))
    async with session.begin():
        tg_id = await consume_challenge(session, code, settings.attribution_bootstrap_admin_tg_ids)
    if tg_id is None:
        return render(
            request,
            "access",
            code=code,
            status_code=403,
            error="Подтвердите код в боте или обновите страницу для получения нового кода.",
        )
    request.session.pop(SESSION_CHALLENGE, None)
    request.session[SESSION_TG_ID] = tg_id
    return RedirectResponse(f"{PREFIX}/links", 303)


@router.get("")
@router.get("/")
async def index(_: Actor) -> Response:
    return RedirectResponse(f"{PREFIX}/links", 303)


def query_filters[T: BaseModel](request: Request, model: type[T]) -> T:
    try:
        return model.model_validate(
            {
                key: value
                for key, value in request.query_params.items()
                if key in model.model_fields and value != ""
            }
        )
    except ValidationError:
        raise HTTPException(422, detail="Проверьте значения фильтров.") from None
