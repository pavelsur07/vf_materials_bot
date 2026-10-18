import re
from collections.abc import AsyncIterator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.admin.app import create_admin_app
from bot.admin.auth import hash_password
from bot.core.config import Settings
from bot.db.models import Base
from bot.integrations.telegram import TelegramChannelAdapter
from bot.modules.leads.use_cases import NotifyLeadUseCase

LEADS_CHAT_ID = -1001
ADMIN_PASSWORD = "admin-pass"


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
        admin_secret_key="test-secret-key",
        admin_password_hash=hash_password(ADMIN_PASSWORD),
        leads_chat_id=LEADS_CHAT_ID,
    )
    use_case = NotifyLeadUseCase(settings, adapter)
    app = create_admin_app(settings, session_factory, use_case)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def disabled_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    settings = Settings(
        admin_secret_key="test-secret-key",
        admin_password_hash=hash_password(ADMIN_PASSWORD),
    )
    app = create_admin_app(settings, session_factory)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login(client: TestClient) -> None:
    csrf = _extract_csrf(client.get("/admin/login").text)
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": ADMIN_PASSWORD, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _dashboard_csrf(client: TestClient) -> str:
    return _extract_csrf(client.get("/admin/").text)


def test_test_button_sends_message(client: TestClient, adapter: TelegramChannelAdapter) -> None:
    _login(client)

    response = client.post(
        "/admin/leads/test",
        data={"csrf_token": _dashboard_csrf(client)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/?lead_test=ok"
    adapter._bot.send_message.assert_awaited_once()
    page = client.get("/admin/?lead_test=ok")
    assert "Тестовое сообщение отправлено" in page.text


def test_test_button_shows_failure(client: TestClient, adapter: TelegramChannelAdapter) -> None:
    _login(client)
    adapter._bot.send_message.side_effect = TelegramAPIError(
        method="sendMessage",
        message="boom",
    )

    response = client.post(
        "/admin/leads/test",
        data={"csrf_token": _dashboard_csrf(client)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/?lead_test=failed"
    page = client.get("/admin/?lead_test=failed")
    assert "Telegram отклонил сообщение" in page.text


def test_test_button_requires_csrf(client: TestClient) -> None:
    _login(client)

    response = client.post("/admin/leads/test", data={}, follow_redirects=False)

    assert response.status_code == 403


def test_test_button_requires_auth(client: TestClient) -> None:
    response = client.post("/admin/leads/test", data={}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_test_button_disabled_when_unconfigured(disabled_client: TestClient) -> None:
    _login(disabled_client)

    response = disabled_client.post(
        "/admin/leads/test",
        data={"csrf_token": _dashboard_csrf(disabled_client)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/?lead_test=disabled"
    page = disabled_client.get("/admin/?lead_test=disabled")
    assert "Релей не настроен" in page.text
