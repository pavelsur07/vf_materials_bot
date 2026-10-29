from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from vashfindir.apps.api.deps import get_templates

router = APIRouter()


@router.get("/api/docs-page", include_in_schema=False)
async def docs_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> Response:
    settings = request.app.state.settings
    return templates.TemplateResponse(
        request=request,
        name="api_docs.html",
        context={
            "docs_path": settings.api_docs_path.strip().strip("/"),
            "base_url": settings.webhook_host.rstrip("/"),
        },
    )
