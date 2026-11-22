from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionSetting, Touch
from vashfindir.domain.attribution.audit import record_change
from vashfindir.domain.attribution.dto import FormValues, TelegramID


class AttributionPreferences(FormValues):
    admin_ids: list[TelegramID] = Field(default_factory=list)
    test_ids: list[TelegramID] = Field(default_factory=list)
    service_chat_id: int = Field(default=0, ge=-(2**63), le=2**63 - 1)
    greeting: str = Field(default="Выберите материал.", min_length=1, max_length=4096)
    dedup_minutes: int = Field(default=10, ge=0, le=1440)
    timezone: str = "Europe/Moscow"
    summary_time: time = time(9)
    warning_percent: int = Field(default=15, ge=0, le=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Укажите часовой пояс IANA, например Europe/Moscow.") from None
        return value

    @field_validator("summary_time")
    @classmethod
    def validate_summary_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("Укажите местное время сводки.")
        return value


async def get_setting(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AttributionSetting, key)
    return row.value if row is not None else None


async def put_setting(session: AsyncSession, key: str, value: str) -> None:
    statement = insert(AttributionSetting).values(key=key, value=value)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[AttributionSetting.key], set_={"value": statement.excluded.value}
        )
    )


async def get_preferences(
    session: AsyncSession, bootstrap_admins: list[int]
) -> AttributionPreferences:
    raw = await get_setting(session, "preferences")
    if raw is None:
        return AttributionPreferences(admin_ids=bootstrap_admins)
    return AttributionPreferences.model_validate_json(raw)


class PreferencesError(ValueError):
    pass


async def save_preferences(
    session: AsyncSession, data: AttributionPreferences, bootstrap_admins: list[int], actor: int
) -> None:
    await session.execute(
        update(AttributionSetting)
        .where(AttributionSetting.key == "preferences")
        .values(value=AttributionSetting.value)
    )
    old = await get_preferences(session, bootstrap_admins)
    old_tests, new_tests = set(old.test_ids), set(data.test_ids)
    for ids, test_mode, message in (
        (new_tests - old_tests, False, "Для тестов выберите ID без боевых касаний."),
        (old_tests - new_tests, True, "Сбросьте историю тестового пользователя перед исключением."),
    ):
        if (
            ids
            and await session.scalar(
                select(Touch.id).where(Touch.tg_id.in_(ids), Touch.is_test.is_(test_mode)).limit(1)
            )
            is not None
        ):
            raise PreferencesError(message)
    await put_setting(session, "preferences", data.model_dump_json())
    record_change(
        session,
        actor,
        "settings",
        "preferences",
        old.model_dump(mode="json"),
        data.model_dump(mode="json"),
    )
