from fastapi import APIRouter, Request
from pydantic import SecretStr, ValidationError
from starlette.responses import RedirectResponse, Response

from vashfindir.apps.admin.auth import verify_csrf
from vashfindir.apps.admin.routes.attribution.access import (
    PREFIX,
    Actor,
    Database,
    config,
    form_data,
    render,
)
from vashfindir.domain.attribution.bitrix_settings import (
    BitrixFields,
    BitrixSettingsError,
    disconnect,
    load_connection,
    load_fields,
    save_connection,
)
from vashfindir.domain.attribution.settings import (
    AttributionPreferences,
    PreferencesError,
    get_preferences,
    save_preferences,
)

router = APIRouter()


@router.get("/settings")
async def settings_page(request: Request, session: Database, _: Actor) -> Response:
    preferences = await get_preferences(session, config(request).attribution_bootstrap_admin_tg_ids)
    return render(request, "settings", preferences=preferences)


@router.post("/settings")
async def change_settings(request: Request, session: Database, actor: Actor) -> Response:
    await verify_csrf(request)
    admins = config(request).attribution_bootstrap_admin_tg_ids
    raw: dict[str, object] = dict(await form_data(request))
    try:
        for field in ("admin_ids", "test_ids"):
            raw[field] = sorted(
                {int(value) for value in str(raw.get(field) or "").replace(",", " ").split()}
            )
        raw["service_chat_id"] = raw.get("service_chat_id") or 0
        preferences = AttributionPreferences.model_validate(raw)
        if not preferences.admin_ids:
            raise ValueError
    except ValueError:
        old = await get_preferences(session, admins)
        return render(
            request,
            "settings",
            status_code=422,
            preferences=old,
            error="Проверьте Telegram ID, часовой пояс, время, интервал и порог.",
        )
    try:
        await save_preferences(session, preferences, admins, actor)
    except PreferencesError as exc:
        await session.rollback()
        return render(
            request,
            "settings",
            status_code=409,
            preferences=preferences,
            error=str(exc),
        )
    await session.commit()
    return RedirectResponse(f"{PREFIX}/settings", 303)


async def bitrix_form(
    request: Request,
    session: Database,
    *,
    status_code: int = 200,
    error: str | None = None,
) -> Response:
    connected = False
    try:
        connected = (
            await load_connection(session, config(request).attribution_secret_key) is not None
        )
    except BitrixSettingsError as exc:
        error = error or str(exc)
    return render(
        request,
        "bitrix",
        status_code=status_code,
        fields=await load_fields(session),
        connected=connected,
        error=error,
    )


@router.get("/bitrix")
async def bitrix_page(request: Request, session: Database, _: Actor) -> Response:
    return await bitrix_form(request, session)


@router.post("/bitrix")
async def change_bitrix(request: Request, session: Database, actor: Actor) -> Response:
    await verify_csrf(request)
    settings = config(request)
    data = await form_data(request)
    webhook = SecretStr(data.pop("webhook", None) or "")
    try:
        fields = BitrixFields.model_validate(data)
        await save_connection(session, settings.attribution_secret_key, fields, webhook, actor)
    except ValidationError:
        return await bitrix_form(
            request,
            session,
            status_code=422,
            error="Укажите источник и пять кодов пользовательских полей UF_CRM_…",
        )
    except BitrixSettingsError as exc:
        return await bitrix_form(request, session, status_code=422, error=str(exc))
    await session.commit()
    return RedirectResponse(f"{PREFIX}/bitrix", 303)


@router.post("/bitrix/disconnect")
async def disconnect_bitrix(request: Request, session: Database, actor: Actor) -> Response:
    await verify_csrf(request)
    await disconnect(session, actor)
    await session.commit()
    return RedirectResponse(f"{PREFIX}/bitrix", 303)
