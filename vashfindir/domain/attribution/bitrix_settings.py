import re
from typing import Annotated
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import Field, SecretStr
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionSetting
from vashfindir.domain.attribution.audit import record_change
from vashfindir.domain.attribution.dto import FormValues
from vashfindir.domain.attribution.settings import get_setting, put_setting

FieldCode = Annotated[str, Field(pattern=r"^UF_CRM_[A-Z0-9_]+$", max_length=64)]


class BitrixFields(FormValues):
    source_id: str = Field(pattern=r"^[A-Za-z0-9_]+$", max_length=64)
    telegram_id: FieldCode
    telegram_username: FieldCode
    first_touch: FieldCode
    last_touch: FieldCode
    magnets: FieldCode


class BitrixConnection(FormValues):
    webhook: SecretStr
    fields: BitrixFields


class BitrixSettingsError(ValueError):
    pass


def _fernet(key: SecretStr) -> Fernet:
    try:
        return Fernet(key.get_secret_value())
    except (ValueError, TypeError):
        raise BitrixSettingsError("Задайте корректный ATTRIBUTION_SECRET_KEY на сервере.") from None


def _normalize_webhook(webhook: SecretStr) -> str:
    raw = webhook.get_secret_value().strip()
    try:
        url = urlsplit(raw)
    except ValueError:
        raise BitrixSettingsError("Укажите полный HTTPS URL входящего вебхука.") from None
    if not (
        url.scheme == "https"
        and url.netloc
        and url.hostname
        and not any(char.isspace() for char in raw)
        and not url.username
        and not url.password
        and not url.query
        and not url.fragment
        and re.fullmatch(r"/rest/[0-9]+/[A-Za-z0-9_-]+/?", url.path)
    ):
        raise BitrixSettingsError("Укажите полный HTTPS URL входящего вебхука.")
    return raw.rstrip("/") + "/"


async def load_fields(session: AsyncSession) -> BitrixFields | None:
    stored = await get_setting(session, "bitrix_fields")
    return BitrixFields.model_validate_json(stored) if stored else None


async def load_connection(session: AsyncSession, key: SecretStr) -> BitrixConnection | None:
    ciphertext = await get_setting(session, "bitrix_webhook")
    fields = await load_fields(session)
    if not ciphertext or fields is None:
        return None
    try:
        webhook = _fernet(key).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise BitrixSettingsError("Не удалось прочитать сохранённый вебхук Bitrix24.") from None
    return BitrixConnection(webhook=SecretStr(webhook), fields=fields)


async def save_connection(
    session: AsyncSession, key: SecretStr, fields: BitrixFields, webhook: SecretStr, actor: int
) -> None:
    if len(set(fields.model_dump(exclude={"source_id"}).values())) != 5:
        raise BitrixSettingsError("Укажите пять разных кодов пользовательских полей.")
    previous = await load_fields(session)
    old_webhook = await get_setting(session, "bitrix_webhook")
    old = previous.model_dump() if previous else {}
    new = fields.model_dump()
    if webhook.get_secret_value().strip():
        ciphertext = _fernet(key).encrypt(_normalize_webhook(webhook).encode()).decode()
        await put_setting(session, "bitrix_webhook", ciphertext)
        old["webhook"] = "configured" if old_webhook else None
        new["webhook"] = "rotated" if old_webhook else "configured"
    await put_setting(session, "bitrix_fields", fields.model_dump_json())
    record_change(session, actor, "settings", "bitrix", old, new)


async def disconnect(session: AsyncSession, actor: int) -> None:
    removed = await session.scalar(
        delete(AttributionSetting)
        .where(AttributionSetting.key == "bitrix_webhook")
        .returning(AttributionSetting.key)
    )
    if removed:
        record_change(
            session,
            actor,
            "settings",
            "bitrix",
            {"webhook": "configured"},
            {"webhook": "disconnected"},
        )
