from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    mode: Literal["polling", "webhook"] = "polling"

    channel_id: int = Field(default=0, alias="TELEGRAM_CHANNEL_ID")
    channel_url: str = Field(default="", alias="TELEGRAM_CHANNEL_URL")
    leadmagnet_url: str = ""

    webhook_host: str = "https://mybots.vashfindir.ru"
    webhook_path: str = "/vashfindir"
    webhook_secret: str = ""

    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8081

    database_url: str = "sqlite+aiosqlite:///./vf_materials_bot.db"

    glitchtip_dsn: str = ""
    glitchtip_environment: str = "production"
    glitchtip_traces_sample_rate: float = 0.0

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host.rstrip('/')}{self.webhook_path}"


def get_settings() -> Settings:
    return Settings()
