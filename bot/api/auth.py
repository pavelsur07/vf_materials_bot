import hmac
from typing import Annotated

from fastapi import Header, HTTPException, Request


def verify_api_token(
    request: Request,
    x_api_token: Annotated[str | None, Header()] = None,
    x_lead_token: Annotated[str | None, Header()] = None,
) -> None:
    """Token auth for machine clients. Accepts x-api-token and legacy x-lead-token.

    LEAD_API_TOKEN принимается наравне с API_TOKEN: сайт-источник лидов не должен
    менять интеграцию при переезде endpoint из админки в сервис api.
    """
    settings = request.app.state.settings
    expected = [t for t in (settings.api_token, settings.lead_api_token) if t]
    if not expected:
        raise HTTPException(status_code=503, detail="API is disabled")
    provided = (x_api_token or x_lead_token or "").encode()
    if not any(hmac.compare_digest(provided, token.encode()) for token in expected):
        raise HTTPException(status_code=401, detail="Invalid token")
