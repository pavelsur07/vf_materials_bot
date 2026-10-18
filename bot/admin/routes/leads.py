from datetime import UTC, datetime

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from bot.admin.auth import verify_csrf
from bot.modules.leads.dialogs import test_message
from bot.modules.leads.dto import LeadNotificationIn
from bot.modules.leads.use_cases import NotifyLeadUseCase

router = APIRouter()


@router.post("/admin/leads/test")
async def test_lead_notification(request: Request) -> RedirectResponse:
    await verify_csrf(request)
    use_case: NotifyLeadUseCase | None = request.app.state.lead_notify_use_case
    if use_case is None:
        return RedirectResponse(url="/admin/?lead_test=disabled", status_code=303)
    reason = await use_case.send(LeadNotificationIn(text=test_message(datetime.now(UTC))))
    target = "ok" if reason is None else "failed"
    return RedirectResponse(url=f"/admin/?lead_test={target}", status_code=303)
