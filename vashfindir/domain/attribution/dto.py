import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

ContentType = Literal["file", "text", "link"]
LinkStatus = Literal["active", "paused", "archived"]
Dictionary = Literal["source", "medium"]
UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


class FormValues(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MagnetInput(FormValues):
    name: str = Field(min_length=1, max_length=100)
    content_type: ContentType
    file_ref: str | None = None
    url: str | None = None
    message: str = Field(default="", max_length=4096)
    is_active: bool = True
    sort: int = 0

    @model_validator(mode="after")
    def validate_content(self) -> "MagnetInput":
        if self.content_type == "text" and not self.message:
            raise ValueError("Укажите текст материала.")
        if self.content_type == "file" and not self.file_ref:
            raise ValueError("Укажите Telegram file_id или путь к файлу.")
        if self.content_type == "link" and not re.fullmatch(r"https?://[^\s]+", self.url or ""):
            raise ValueError("Укажите ссылку, начинающуюся с https:// или http://.")
        return self


class NewMagnetInput(MagnetInput):
    prefix: str = Field(pattern=r"^[a-z0-9]{2,10}$")


class DictValueInput(FormValues):
    value: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    label: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    sort: int = 0

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return value.strip().lower()


class LinkChanges(FormValues):
    placement: str = Field(min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    budget: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    status: LinkStatus = "active"
    comment: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_period(self) -> "LinkChanges":
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("Дата окончания должна быть не раньше даты начала.")
        return self


Tag = Annotated[str, Field(max_length=64, pattern=r"^[a-z0-9_]+$")]


class LinkInput(LinkChanges):
    lead_magnet_id: int = Field(gt=0)
    utm_source: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    utm_medium: str = Field(pattern=r"^[a-z0-9_]{1,32}$")
    utm_campaign: Tag
    utm_content: Tag | None = None
    utm_term: Tag | None = None

    @field_validator("utm_campaign", "utm_content", "utm_term", mode="before")
    @classmethod
    def normalize_tag(cls, value: object) -> object:
        if isinstance(value, str):
            return re.sub(r"\s+", "_", value.strip().lower()) or None
        return value


TelegramID = Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]
