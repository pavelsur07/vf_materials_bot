from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from vashfindir.apps.admin.auth import issue_csrf_token
from vashfindir.apps.admin.deps import get_session, get_templates
from vashfindir.domain.stats import count_users, list_recent_users
from vashfindir.modules.leads.dialogs import TEST_MESSAGES

router = APIRouter(prefix="/admin")


@router.get("/")
async def dashboard(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    templates = get_templates(request)
    lead_test = request.query_params.get("lead_test")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "csrf_token": issue_csrf_token(request),
            "total_users": await count_users(session),
            "users": await list_recent_users(session),
            "lead_test_message": TEST_MESSAGES.get(lead_test) if lead_test else None,
            "lead_test_ok": lead_test == "ok",
        },
    )
