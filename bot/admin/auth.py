import hmac
import secrets

import bcrypt
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp

SESSION_USER_KEY = "admin_user"
CSRF_SESSION_KEY = "csrf_token"
LOGIN_PATH = "/admin/login"
HEALTH_PATH = "/admin/health"
LEADS_PATH = "/api/leads"
PUBLIC_PATHS = {LOGIN_PATH, HEALTH_PATH, LEADS_PATH}


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def credentials_valid(
    username: str, password: str, expected_username: str, password_hash: str
) -> bool:
    user_ok = hmac.compare_digest(username.encode(), expected_username.encode())
    return user_ok and verify_password(password, password_hash)


def issue_csrf_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


async def verify_csrf(request: Request) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    form = await request.form()
    provided = str(form.get("csrf_token", ""))
    if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirects anonymous users to the login page, except for public paths."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        if request.session.get(SESSION_USER_KEY) is None:
            return RedirectResponse(url=LOGIN_PATH, status_code=303)
        return await call_next(request)
