import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import PlainTextResponse, RedirectResponse

from bot.admin.auth import verify_csrf
from bot.modules.leads.dialogs import test_message
from bot.modules.leads.dto import LeadNotificationIn
from bot.modules.leads.use_cases import NotifyLeadUseCase

router = APIRouter()


@router.post("/api/leads")
async def create_lead_notification(request: Request, data: LeadNotificationIn) -> PlainTextResponse:
    settings = request.app.state.settings
    use_case: NotifyLeadUseCase | None = request.app.state.lead_notify_use_case
    if use_case is None or not settings.lead_api_token:
        raise HTTPException(status_code=503, detail="Lead notifications are disabled")
    provided = request.headers.get("x-lead-token", "")
    if not hmac.compare_digest(provided.encode(), settings.lead_api_token.encode()):
        raise HTTPException(status_code=401, detail="Invalid token")
    reason = await use_case.send(data)
    if reason is not None:
        raise HTTPException(status_code=502, detail=reason)
    return PlainTextResponse("ok")


@router.post("/admin/leads/test")
async def test_lead_notification(request: Request) -> RedirectResponse:
    await verify_csrf(request)
    use_case: NotifyLeadUseCase | None = request.app.state.lead_notify_use_case
    if use_case is None:
        return RedirectResponse(url="/admin/?lead_test=disabled", status_code=303)
    reason = await use_case.send(LeadNotificationIn(text=test_message(datetime.now(UTC))))
    target = "ok" if reason is None else "failed"
    return RedirectResponse(url=f"/admin/?lead_test={target}", status_code=303)
