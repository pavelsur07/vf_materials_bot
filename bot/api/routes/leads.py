from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import PlainTextResponse

from bot.api.auth import verify_api_token
from bot.modules.leads.dto import LeadNotificationIn
from bot.modules.leads.use_cases import NotifyLeadUseCase

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.post("/api/leads")
async def create_lead_notification(request: Request, data: LeadNotificationIn) -> PlainTextResponse:
    use_case: NotifyLeadUseCase | None = request.app.state.lead_notify_use_case
    if use_case is None:
        raise HTTPException(status_code=503, detail="Lead notifications are disabled")
    reason = await use_case.send(data)
    if reason is not None:
        raise HTTPException(status_code=502, detail=reason)
    return PlainTextResponse("ok")
