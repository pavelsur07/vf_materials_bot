import re
from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vashfindir.apps.admin.app import create_admin_app
from vashfindir.apps.admin.auth import hash_password
from vashfindir.core.config import Settings
from vashfindir.db.models import Base, User

ADMIN_PASSWORD = "admin-pass"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(User(tg_id=1, username="alice", first_name="Alice"))
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def client(session_factory: async_sessionmaker[AsyncSession]) -> Generator[TestClient, None, None]:
    settings = Settings(
        admin_secret_key="test-secret-key",
        admin_username="admin",
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
    assert response.headers["location"] == "/admin/"


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/admin/health")
    assert response.status_code == 200
    assert response.text == "ok"


def test_anonymous_redirected_to_login(client: TestClient) -> None:
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_login_page_renders(client: TestClient) -> None:
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text


def test_login_wrong_password(client: TestClient) -> None:
    csrf = _extract_csrf(client.get("/admin/login").text)
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong", "csrf_token": csrf},
    )
    assert response.status_code == 401
    assert "Неверный логин или пароль" in response.text


def test_login_rejects_missing_csrf(client: TestClient) -> None:
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 403


def test_dashboard_shows_users(client: TestClient) -> None:
    _login(client)
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "Всего: 1" in response.text
    assert "alice" in response.text


def test_logout(client: TestClient) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/").text)
    response = client.post("/admin/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert response.status_code == 303

    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
