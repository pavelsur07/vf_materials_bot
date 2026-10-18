from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    mode: Literal["polling", "webhook"] = "polling"

    channel_id: int = Field(default=0, alias="TELEGRAM_CHANNEL_ID")
    channel_url: str = Field(default="", alias="TELEGRAM_CHANNEL_URL")
    leadmagnet_url: str = ""

    # Релей уведомлений о лидах: сайт на RU-хостинге не достаёт до api.telegram.org
    # (блокировка), поэтому шлёт готовый текст сюда, а бот пересылает его в Telegram.
    lead_api_token: str = ""
    leads_chat_id: int = 0
    leads_topic_id: int = 0

    webhook_host: str = "https://mybots.vashfindir.ru"
    webhook_path: str = "/vashfindir"
    webhook_secret: str = ""

    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8081

    admin_host: str = "127.0.0.1"
    admin_port: int = 8082
    admin_secret_key: str = ""
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # Публичный API для бизнес-интеграций (python -m bot.api)
    api_host: str = "127.0.0.1"
    api_port: int = 8083
    api_token: str = ""

    database_url: str = "sqlite+aiosqlite:///./vf_materials_bot.db"

    glitchtip_dsn: str = ""
    glitchtip_environment: str = "production"
    glitchtip_traces_sample_rate: float = 0.0

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host.rstrip('/')}{self.webhook_path}"

    @field_validator("leads_chat_id", "leads_topic_id", mode="before")
    @classmethod
    def _blank_int_to_zero(cls, value: object) -> object:
        # Пустая строка в .env (= «не задано») означает 0, а не ошибку парсинга int
        return 0 if value == "" else value


def get_settings() -> Settings:
    return Settings()
