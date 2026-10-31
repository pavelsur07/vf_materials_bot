from collections.abc import AsyncIterator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vashfindir.apps.api.app import create_api_app
from vashfindir.core.config import Settings
from vashfindir.db.models import Base
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.modules.leads.use_cases import NotifyLeadUseCase

API_TOKEN = "api-secret"
LEGACY_TOKEN = "lead-secret"
LEADS_CHAT_ID = -1001


@pytest.fixture
def adapter() -> TelegramChannelAdapter:
    return TelegramChannelAdapter(AsyncMock(spec=Bot))


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def client(
    session_factory: async_sessionmaker[AsyncSession], adapter: TelegramChannelAdapter
) -> Generator[TestClient, None, None]:
    settings = Settings(
        api_token=API_TOKEN,
        lead_api_token=LEGACY_TOKEN,
        leads_chat_id=LEADS_CHAT_ID,
    )
    use_case = NotifyLeadUseCase(settings, adapter)
    app = create_api_app(settings, session_factory, use_case)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def disabled_client(
    session_factory: async_sessionmaker[AsyncSession], adapter: TelegramChannelAdapter
) -> Generator[TestClient, None, None]:
    settings = Settings(api_token="", lead_api_token="")
    use_case = NotifyLeadUseCase(settings, adapter)
    app = create_api_app(settings, session_factory, use_case)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def no_use_case_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    settings = Settings(api_token=API_TOKEN, leads_chat_id=0)
    app = create_api_app(settings, session_factory)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.text == "ok"


def test_telegram_bot_closed_on_shutdown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    telegram_bot = AsyncMock()
    app = create_api_app(
        Settings(_env_file=None),
        session_factory,
        telegram_bot=telegram_bot,
    )

    with TestClient(app, base_url="https://testserver"):
        pass

    telegram_bot.session.close.assert_awaited_once()


def test_lead_notification_accepted_with_api_token(
    client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    response = client.post(
        "/api/leads",
        json={"text": "Новое обращение №17"},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 200
    assert response.text == "ok"
    adapter._bot.send_message.assert_awaited_once()


def test_lead_notification_accepted_with_legacy_lead_token(
    client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    response = client.post(
        "/api/leads",
        json={"text": "Новое обращение №18"},
        headers={"X-Lead-Token": LEGACY_TOKEN},
    )

    assert response.status_code == 200
    adapter._bot.send_message.assert_awaited_once()


def test_lead_notification_rejects_invalid_token(
    client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    response = client.post(
        "/api/leads",
        json={"text": "Новое обращение №17"},
        headers={"X-API-Token": "wrong-token"},
    )

    assert response.status_code == 401
    adapter._bot.send_message.assert_not_awaited()


def test_lead_notification_rejects_missing_token(
    client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    response = client.post("/api/leads", json={"text": "Новое обращение №17"})

    assert response.status_code == 401
    adapter._bot.send_message.assert_not_awaited()


def test_lead_notification_returns_502_when_telegram_fails(
    client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    adapter._bot.send_message.side_effect = TelegramAPIError(
        method="sendMessage",
        message="boom",
    )

    response = client.post(
        "/api/leads",
        json={"text": "Новое обращение №17"},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 502


def test_lead_notification_disabled_when_no_token_configured(
    disabled_client: TestClient, adapter: TelegramChannelAdapter
) -> None:
    response = disabled_client.post(
        "/api/leads",
        json={"text": "Новое обращение №17"},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 503
    adapter._bot.send_message.assert_not_awaited()


def test_lead_notification_disabled_when_use_case_not_configured(
    no_use_case_client: TestClient,
) -> None:
    response = no_use_case_client.post(
        "/api/leads",
        json={"text": "Новое обращение №17"},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 503


def test_lead_notification_rejects_oversized_text(client: TestClient) -> None:
    response = client.post(
        "/api/leads",
        json={"text": "x" * 4001},
        headers={"X-API-Token": API_TOKEN},
    )

    assert response.status_code == 422
