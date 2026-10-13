from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse, Response

from bot.admin.auth import (
    SESSION_USER_KEY,
    credentials_valid,
    issue_csrf_token,
    verify_csrf,
)
from bot.admin.deps import get_templates

router = APIRouter(prefix="/admin")


@router.get("/login")
async def login_form(request: Request) -> Response:
    templates = get_templates(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": issue_csrf_token(request)},
    )


@router.post("/login")
async def login_submit(request: Request) -> Response:
    await verify_csrf(request)
    templates = get_templates(request)
    settings = request.app.state.settings
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    if not credentials_valid(
        username, password, settings.admin_username, settings.admin_password_hash
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "csrf_token": issue_csrf_token(request),
                "error": "Неверный логин или пароль",
            },
            status_code=401,
        )

    request.session[SESSION_USER_KEY] = username
    issue_csrf_token(request)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/logout")
async def logout(request: Request) -> Response:
    await verify_csrf(request)
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)
