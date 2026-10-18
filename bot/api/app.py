from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import PlainTextResponse

from bot.api.routes import leads
from bot.core.config import Settings
from bot.modules.leads.use_cases import NotifyLeadUseCase


def create_api_app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    lead_notify_use_case: NotifyLeadUseCase | None = None,
) -> FastAPI:
    app = FastAPI(title="VF API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.lead_notify_use_case = lead_notify_use_case

    app.include_router(leads.router)

    @app.get("/healthz")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app
