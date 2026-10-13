from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from bot.admin.auth import issue_csrf_token
from bot.admin.deps import get_session, get_templates
from bot.services.stats import count_users, list_recent_users

router = APIRouter(prefix="/admin")


@router.get("/")
async def dashboard(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    templates = get_templates(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "csrf_token": issue_csrf_token(request),
            "total_users": await count_users(session),
            "users": await list_recent_users(session),
        },
    )
