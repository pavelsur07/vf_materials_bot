from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import PlainTextResponse

from bot.api.routes import docs, leads
from bot.core.config import Settings
from bot.modules.leads.use_cases import NotifyLeadUseCase

TEMPLATES_DIR = Path(__file__).parent / "templates"

API_DESCRIPTION = (
    "Публичный API платформы «Ваш Финдир» для бизнес-интеграций. "
    "Аутентификация — токен в заголовке `x-api-token` (принимается и legacy `x-lead-token`)."
)


def create_api_app(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    lead_notify_use_case: NotifyLeadUseCase | None = None,
) -> FastAPI:
    # Пустой api_docs_path — docs выключены; иначе Swagger UI живёт ровно на этом
    # пути, ReDoc и openapi.json — под ним. nginx закрывает ветку basic auth'ом.
    raw_docs_path = settings.api_docs_path.strip().strip("/")
    docs_root = f"/{raw_docs_path}" if raw_docs_path else ""

    app = FastAPI(
        title="VF API",
        description=API_DESCRIPTION,
        version="1.0.0",
        docs_url=docs_root or None,
        redoc_url=f"{docs_root}/redoc" if docs_root else None,
        openapi_url=f"{docs_root}/openapi.json" if docs_root else None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.lead_notify_use_case = lead_notify_use_case
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

    app.include_router(leads.router)
    if docs_root:
        app.include_router(docs.router)

    @app.get("/healthz")
    async def health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return app
