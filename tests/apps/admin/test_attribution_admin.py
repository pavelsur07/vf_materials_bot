import re
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vashfindir.apps.admin.app import create_admin_app
from vashfindir.apps.admin.auth import hash_password
from vashfindir.core.config import Settings
from vashfindir.db.models import AttributionSetting, AuditLog


@pytest_asyncio.fixture
async def admin(
    session: AsyncSession,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    app = create_admin_app(
        Settings(
            _env_file=None,
            attribution_enabled=True,
            admin_username="admin",
            admin_password_hash=hash_password("unit-test-password"),
            admin_secret_key="test",
            attribution_bootstrap_admin_tg_ids=[123],
            attribution_secret_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
            attribution_bot_username="example_bot",
        ),
        factory,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        login = await client.get("/admin/login")
        await client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": "unit-test-password",
                "csrf_token": csrf(login.text),
            },
        )
        yield client, factory


def csrf(html: str) -> str:
    found = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert found is not None
    return found[1]


async def authenticate(client: AsyncClient, factory: async_sessionmaker[AsyncSession]) -> None:
    from vashfindir.domain.attribution.admin_access import approve_challenge

    page = await client.get("/admin/attribution/access")
    code = re.search(r"/admin_auth ([\w-]+)", page.text)
    assert code is not None
    async with factory.begin() as session:
        assert not await approve_challenge(session, code[1], 222, [123])
        assert await approve_challenge(session, code[1], 123, [123])
        assert not await approve_challenge(session, code[1], 123, [123])
    response = await client.post("/admin/attribution/access", data={"csrf_token": csrf(page.text)})
    assert response.status_code == 303


@pytest.mark.asyncio
async def test_bitrix_settings_encrypt_webhook_and_never_render_it(admin) -> None:
    client, factory = admin
    url = "/admin/attribution/bitrix"
    assert (await client.get(url)).status_code == 303
    await authenticate(client, factory)

    page = await client.get(url)
    webhook = "https://example.bitrix24.ru/rest/13/webhook-secret/"
    values = {
        "webhook": webhook,
        "source_id": "TELEGRAM",
        "telegram_id": "UF_CRM_TG_ID",
        "telegram_username": "UF_CRM_TG_USERNAME",
        "first_touch": "UF_CRM_FIRST",
        "last_touch": "UF_CRM_LAST",
        "magnets": "UF_CRM_MAGNETS",
    }
    assert (await client.post(url, data=values)).status_code == 403
    result = await client.post(url, data={**values, "csrf_token": csrf(page.text)})
    assert result.status_code == 303, result.text
    updated = await client.get(url)
    assert "Вебхук сохранён" in updated.text
    assert webhook not in updated.text
    assert "webhook-secret" not in updated.text
    async with factory() as session:
        stored = (await session.scalars(select(AttributionSetting))).all()
        assert len(stored) == 2
        assert all("webhook-secret" not in row.value for row in stored)
        audit = (await session.scalars(select(AuditLog))).all()
        assert len(audit) == 1 and audit[0].actor_tg_id == 123
        assert "webhook-secret" not in audit[0].changes


@pytest.mark.asyncio
async def test_link_creation_reports_duplicate_and_forbids_editing_utm(admin) -> None:
    from vashfindir.db.models import AttributionLink, DictValue, LeadMagnet

    client, factory = admin
    await authenticate(client, factory)
    async with factory.begin() as session:
        session.add_all(
            [
                LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Текст"),
                DictValue(dict="source", value="tg", label="Telegram"),
                DictValue(dict="medium", value="post", label="Публикация"),
            ]
        )
    url = "/admin/attribution/links/new"
    form = await client.get(url)
    data = {
        "csrf_token": csrf(form.text),
        "lead_magnet_id": "1",
        "utm_source": "tg",
        "utm_medium": "post",
        "utm_campaign": "SUMMER offer",
        "placement": "Канал",
    }
    assert (await client.post(url, data=data)).status_code == 303
    duplicate = await client.post(url, data=data)
    assert duplicate.status_code == 409
    assert "dds_001" in duplicate.text
    assert 'name="confirm_duplicate"' in duplicate.text
    qr = await client.get("/admin/attribution/links/1/qr.png")
    assert qr.headers.get("content-type") == "image/png"
    assert qr.content.startswith(b"\x89PNG\r\n\x1a\n")
    edit = await client.get("/admin/attribution/links/1")
    changed = await client.post(
        "/admin/attribution/links/1",
        data={
            "csrf_token": csrf(edit.text),
            "placement": "Размещение",
            "utm_campaign": "manipulated",
        },
    )
    assert changed.status_code == 422
    async with factory() as session:
        link = await session.get(AttributionLink, 1)
        assert link is not None and link.utm_campaign == "summer_offer"
