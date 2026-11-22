from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    first_touch_id: Mapped[int | None] = mapped_column(
        ForeignKey("touches.id", name="fk_users_first_touch", use_alter=True)
    )
    last_touch_id: Mapped[int | None] = mapped_column(
        ForeignKey("touches.id", name="fk_users_last_touch", use_alter=True)
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bitrix_lead_id: Mapped[int | None] = mapped_column(BigInteger)
    is_blocked: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    """Очередь фоновых задач: сервисы кладут (enqueue), воркер забирает (claim)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)


class SlideGeneration(Base):
    """One requested slide image and its lifecycle metadata."""

    __tablename__ = "slide_generations"

    id: Mapped[int] = mapped_column(primary_key=True)
    plot: Mapped[str] = mapped_column(Text)
    style_id: Mapped[str] = mapped_column(String(32), default="style_01", index=True)
    style_version: Mapped[int]
    model: Mapped[str] = mapped_column(String(128))
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text)
    provider_request_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    original_path: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadMagnet(Base):
    __tablename__ = "lead_magnets"
    __table_args__ = (
        CheckConstraint("content_type IN ('file', 'text', 'link')", name="ck_magnet_content"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    content_type: Mapped[str] = mapped_column(String(4))
    file_ref: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    sort: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DictValue(Base):
    __tablename__ = "dict_values"
    __table_args__ = (
        UniqueConstraint("dict", "value", name="uq_dict_value"),
        CheckConstraint("dict IN ('source', 'medium')", name="ck_dict_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dict: Mapped[str] = mapped_column(String(6))
    value: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    sort: Mapped[int] = mapped_column(default=0, server_default="0")


class AttributionLink(Base):
    __tablename__ = "links"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'archived')", name="ck_link_status"),
        Index("ix_links_campaign", "utm_campaign"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    lead_magnet_id: Mapped[int] = mapped_column(ForeignKey("lead_magnets.id"), index=True)
    utm_source: Mapped[str] = mapped_column(String(32))
    utm_medium: Mapped[str] = mapped_column(String(32))
    utm_campaign: Mapped[str] = mapped_column(String(64))
    utm_content: Mapped[str | None] = mapped_column(String(64))
    utm_term: Mapped[str | None] = mapped_column(String(64))
    placement: Mapped[str] = mapped_column(String(255))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(8), default="active", server_default="active")
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Touch(Base):
    __tablename__ = "touches"
    __table_args__ = (
        CheckConstraint("code_status IN ('ok', 'unknown', 'direct')", name="ck_touch_code_status"),
        CheckConstraint(
            "magnet_source IN ('link', 'prefix', 'menu')", name="ck_touch_magnet_source"
        ),
        CheckConstraint(
            "bitrix_status IN ('pending', 'ok', 'error', 'skipped')", name="ck_touch_bitrix_status"
        ),
        Index("ix_touches_user_payload", "tg_id", "payload_digest", "created_at"),
        Index("ix_touches_bitrix_due", "bitrix_status", "bitrix_next_attempt_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id"), index=True)
    raw_payload: Mapped[str | None] = mapped_column(String(64))
    payload_digest: Mapped[str] = mapped_column(String(64))
    link_id: Mapped[int | None] = mapped_column(ForeignKey("links.id"), index=True)
    code_status: Mapped[str] = mapped_column(String(7))
    lead_magnet_id: Mapped[int | None] = mapped_column(ForeignKey("lead_magnets.id"), index=True)
    magnet_source: Mapped[str | None] = mapped_column(String(6))
    utm_source: Mapped[str] = mapped_column(String(32))
    utm_medium: Mapped[str | None] = mapped_column(String(32))
    utm_campaign: Mapped[str | None] = mapped_column(String(64))
    utm_content: Mapped[str | None] = mapped_column(String(64))
    utm_term: Mapped[str | None] = mapped_column(String(64))
    is_new_user: Mapped[bool]
    is_test: Mapped[bool] = mapped_column(default=False, server_default=false())
    magnet_delivered: Mapped[bool] = mapped_column(default=False, server_default=false())
    delivery_finished: Mapped[bool] = mapped_column(default=False, server_default=false())
    bitrix_status: Mapped[str] = mapped_column(
        String(7), default="pending", server_default="pending"
    )
    bitrix_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    bitrix_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bitrix_error: Mapped[str | None] = mapped_column(Text)
    bitrix_comment_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_tg_id: Mapped[int] = mapped_column(BigInteger)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(100))
    changes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttributionSetting(Base):
    __tablename__ = "attribution_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
