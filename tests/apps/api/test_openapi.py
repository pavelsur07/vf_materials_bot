from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vashfindir.apps.api.app import create_api_app
from vashfindir.core.config import Settings
from vashfindir.db.models import Base

DOCS_PATH = "/api/docs"
API_TOKEN = "api-secret"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def docs_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    # _env_file=None: тест не должен зависеть от локального .env разработчика
    settings = Settings(api_token=API_TOKEN, api_docs_path=DOCS_PATH, _env_file=None)
    app = create_api_app(settings, session_factory)
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def test_swagger_ui_available(docs_client: TestClient) -> None:
    response = docs_client.get(DOCS_PATH)

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_redoc_available(docs_client: TestClient) -> None:
    response = docs_client.get(f"{DOCS_PATH}/redoc")

    assert response.status_code == 200
    assert "redoc" in response.text.lower()


def test_openapi_schema_describes_public_contract(docs_client: TestClient) -> None:
    response = docs_client.get(f"{DOCS_PATH}/openapi.json")

    assert response.status_code == 200
    schema = response.json()

    assert schema["info"]["title"] == "VF API"
    assert "/api/leads" in schema["paths"]
    operation = schema["paths"]["/api/leads"]["post"]
    assert "Leads" in operation["tags"]
    assert {"401", "502", "503"} <= set(operation["responses"])

    security_schemes = schema["components"]["securitySchemes"]
    assert "ApiKeyAuth" in security_schemes
    assert security_schemes["ApiKeyAuth"]["in"] == "header"
    assert any("ApiKeyAuth" in requirement for requirement in operation["security"])

    lead_schema = schema["components"]["schemas"]["LeadNotificationIn"]
    assert lead_schema["examples"]


def test_docs_disabled_by_default(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # _env_file=None: иначе локальный .env разработчика может включить docs
    settings = Settings(api_token=API_TOKEN, _env_file=None)  # api_docs_path=""
    app = create_api_app(settings, session_factory)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get(DOCS_PATH).status_code == 404
        assert client.get(f"{DOCS_PATH}/openapi.json").status_code == 404
        assert client.get("/api/docs-page").status_code == 404


def test_quickstart_page(docs_client: TestClient) -> None:
    response = docs_client.get("/api/docs-page")

    assert response.status_code == 200
    assert "x-api-token" in response.text
    assert "/api/leads" in response.text
