from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse

from bot.admin.auth import AuthMiddleware
from bot.admin.routes import auth_pages, pages
from bot.core.config import Settings

TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_admin_app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> FastAPI:
    app = FastAPI(title="VF Admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

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

    @app.get("/admin/health")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app
