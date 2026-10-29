from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse

from vashfindir.apps.admin.auth import AuthMiddleware
from vashfindir.apps.admin.routes import auth_pages, leads, pages
from vashfindir.core.config import Settings
from vashfindir.modules.leads.use_cases import NotifyLeadUseCase

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_admin_app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    lead_notify_use_case: NotifyLeadUseCase | None = None,
) -> FastAPI:
    app = FastAPI(title="VF Admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.state.lead_notify_use_case = lead_notify_use_case

    # Starlette runs the last added middleware first, so SessionMiddleware
    # wraps AuthMiddleware and request.session is already populated there.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_secret_key,
        https_only=True,
        same_site="lax",
    )

    app.include_router(auth_pages.router)
    app.include_router(pages.router)
    app.include_router(leads.router)

    @app.get("/admin/health")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app
