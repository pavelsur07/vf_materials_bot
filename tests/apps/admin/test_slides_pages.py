import asyncio
import re
from collections.abc import AsyncIterator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import vashfindir.domain.slides as slides_domain
from vashfindir.apps.admin.app import create_admin_app
from vashfindir.apps.admin.auth import hash_password
from vashfindir.apps.worker.handlers import GENERATE_SLIDE_JOB_TYPE, build_handlers
from vashfindir.core.config import Settings
from vashfindir.db.models import Base, Job
from vashfindir.domain.slides import (
    SlideStyleId,
    create_slide_generation,
    default_slide_style,
    get_result_slide_path,
    mark_slide_generation_ready,
)
from vashfindir.integrations.mock_image_generator import MockImageGenerator
from vashfindir.modules.slides.use_cases import QueueSlideGenerationUseCase

ADMIN_PASSWORD = "admin-pass"
PLOT = "Финансовый директор анализирует падение выручки компании"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def ready_session_factory(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    root = tmp_path / "generated" / "slides"
    monkeypatch.setattr(slides_domain, "GENERATED_SLIDES_ROOT", root)
    async with session_factory() as session:
        generation = await create_slide_generation(
            session,
            plot=PLOT,
            style_id=SlideStyleId.STYLE_01,
            style_version=1,
            model="mock-model",
            prompt="Visual subject: test",
            negative_prompt="text",
            author="admin",
        )
        result_path = get_result_slide_path(generation.id)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_bytes(b"ready png")
        await mark_slide_generation_ready(
            session,
            generation,
            image_path=str(result_path),
            original_path=str(result_path),
            provider_request_id="provider-1",
        )
    yield session_factory


def _make_client(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    enable_slides: bool = True,
) -> TestClient:
    settings = Settings(
        admin_secret_key="test-secret-key",
        admin_username="admin",
        admin_password_hash=hash_password(ADMIN_PASSWORD),
    )
    slide_use_case = QueueSlideGenerationUseCase(default_slide_style()) if enable_slides else None
    app = create_admin_app(
        settings,
        session_factory,
        slide_generation_use_case=slide_use_case,
    )
    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def client(
    session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(
        slides_domain,
        "GENERATED_SLIDES_ROOT",
        tmp_path / "generated" / "slides",
    )
    with _make_client(session_factory) as test_client:
        yield test_client


@pytest.fixture
def ready_client(
    ready_session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    with _make_client(ready_session_factory) as test_client:
        yield test_client


@pytest.fixture
def disabled_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> Generator[TestClient, None, None]:
    with _make_client(session_factory, enable_slides=False) as test_client:
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


def test_slides_page_requires_auth(client: TestClient) -> None:
    response = client.get("/admin/slides", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_dashboard_has_slides_navigation(client: TestClient) -> None:
    _login(client)

    response = client.get("/admin/")

    assert response.status_code == 200
    assert 'href="/admin/slides"' in response.text
    assert "button.disabled = true;" in response.text


def test_slides_page_renders_form_and_empty_history(client: TestClient) -> None:
    _login(client)

    response = client.get("/admin/slides")

    assert response.status_code == 200
    assert 'name="plot"' in response.text
    assert "История генераций" in response.text
    assert "Пока нет генераций" in response.text


def test_create_generation_queues_job_and_redirects_to_detail(client: TestClient) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/slides").text)

    response = client.post(
        "/admin/slides",
        data={"plot": PLOT, "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/slides/1?created=1"

    detail = client.get("/admin/slides/1")
    assert detail.status_code == 200
    assert "Генерация №1" in detail.text
    assert PLOT in detail.text
    assert "В очереди" in detail.text
    assert "Задача создана и ждёт запуска worker." in detail.text
    assert "Страница обновится автоматически" in detail.text
    assert "setTimeout(() => window.location.reload(), 5000);" in detail.text
    assert (
        "Генерация уже выполняется. Повторный запуск будет доступен после завершения."
        in detail.text
    )
    assert "Сгенерировать ещё раз" not in detail.text

    history = client.get("/admin/slides")
    assert "В очереди" in history.text
    assert PLOT[:40] in history.text


def test_create_generation_rejects_invalid_plot(client: TestClient) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/slides").text)

    response = client.post(
        "/admin/slides",
        data={"plot": "коротко", "csrf_token": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/slides?invalid_plot=1"
    page = client.get("/admin/slides?invalid_plot=1")
    assert "от 10 до 1000 символов" in page.text
    assert "Пока нет генераций" in page.text


def test_create_generation_requires_csrf(client: TestClient) -> None:
    _login(client)

    response = client.post("/admin/slides", data={"plot": PLOT}, follow_redirects=False)

    assert response.status_code == 403


def test_detail_page_returns_404_for_unknown_generation(client: TestClient) -> None:
    _login(client)

    response = client.get("/admin/slides/999")

    assert response.status_code == 404


def test_retry_creates_new_generation(ready_client: TestClient) -> None:
    _login(ready_client)

    detail = ready_client.get("/admin/slides/1")
    retry_csrf = _extract_csrf(detail.text)
    response = ready_client.post(
        "/admin/slides/1/retry",
        data={"csrf_token": retry_csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/slides/2?created=1"
    new_detail = ready_client.get("/admin/slides/2")
    assert "Генерация №2" in new_detail.text
    assert PLOT in new_detail.text
    assert "Сгенерировать ещё раз" not in new_detail.text


def test_retry_is_rejected_while_generation_is_active(client: TestClient) -> None:
    _login(client)
    create_csrf = _extract_csrf(client.get("/admin/slides").text)
    created = client.post(
        "/admin/slides",
        data={"plot": PLOT, "csrf_token": create_csrf},
        follow_redirects=False,
    )
    assert created.status_code == 303

    detail = client.get("/admin/slides/1")
    retry_csrf = _extract_csrf(detail.text)
    response = client.post(
        "/admin/slides/1/retry",
        data={"csrf_token": retry_csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/slides/1?already_running=1"
    detail = client.get("/admin/slides/1?already_running=1")
    assert "Генерация уже выполняется. Дождитесь завершения." in detail.text
    assert "Сгенерировать ещё раз" not in detail.text


def test_retry_requires_csrf(client: TestClient) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/slides").text)
    client.post("/admin/slides", data={"plot": PLOT, "csrf_token": csrf})

    response = client.post("/admin/slides/1/retry", data={}, follow_redirects=False)

    assert response.status_code == 403


def test_ready_page_shows_result_and_downloads_png(ready_client: TestClient) -> None:
    _login(ready_client)

    detail = ready_client.get("/admin/slides/1")
    assert detail.status_code == 200
    assert "Готово" in detail.text
    assert "Изображение готово и доступно для скачивания." in detail.text
    assert "provider-1" in detail.text
    assert "Скачать PNG" in detail.text
    assert 'src="/admin/slides/1/download"' in detail.text
    assert "Сгенерировать ещё раз" in detail.text
    assert "window.location.reload()" not in detail.text

    download = ready_client.get("/admin/slides/1/download")
    assert download.status_code == 200
    assert download.content == b"ready png"
    assert download.headers["content-type"].startswith("image/png")
    assert "slide-1.png" in download.headers["content-disposition"]


def test_download_returns_404_until_generation_is_ready(client: TestClient) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/slides").text)
    client.post("/admin/slides", data={"plot": PLOT, "csrf_token": csrf})

    response = client.get("/admin/slides/1/download")

    assert response.status_code == 404


async def _process_queued_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        job = await session.scalar(select(Job).where(Job.type == GENERATE_SLIDE_JOB_TYPE))
        assert job is not None
        await build_handlers(MockImageGenerator())[GENERATE_SLIDE_JOB_TYPE](job, session)


def test_admin_submission_is_processed_by_worker_and_can_be_downloaded(
    client: TestClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _login(client)
    csrf = _extract_csrf(client.get("/admin/slides").text)
    created = client.post(
        "/admin/slides",
        data={"plot": PLOT, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert created.status_code == 303

    asyncio.run(_process_queued_job(session_factory))

    detail = client.get("/admin/slides/1")
    assert detail.status_code == 200
    assert "Готово" in detail.text

    download = client.get("/admin/slides/1/download")
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_slides_form_is_hidden_when_use_case_is_not_configured(
    disabled_client: TestClient,
) -> None:
    _login(disabled_client)

    response = disabled_client.get("/admin/slides")

    assert response.status_code == 200
    assert 'name="plot"' not in response.text
