from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Integer, Row, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, DictValue, LeadMagnet, Touch, User
from vashfindir.domain.attribution.catalog import active_magnets
from vashfindir.domain.attribution.dto import Dictionary
from vashfindir.domain.jobs import utcnow

PAGE_SIZE = 100


def utc_boundary(value: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(value, time.min, zone).astimezone(UTC).replace(tzinfo=None)


class DateWindow(BaseModel):
    start: date | None = Field(default=None, ge=date(1900, 1, 1))
    end: date | None = Field(default=None, ge=date(1900, 1, 1))

    @model_validator(mode="after")
    def validate_window(self) -> "DateWindow":
        if self.start and self.end and self.start > self.end:
            raise ValueError("Дата окончания должна быть не раньше даты начала.")
        return self

    def lower(self, zone: ZoneInfo) -> datetime | None:
        return utc_boundary(self.start, zone) if self.start else None

    def upper(self, zone: ZoneInfo) -> datetime | None:
        if self.end is None or self.end == date.max:
            return None
        return utc_boundary(self.end + timedelta(days=1), zone)


class LinkFilter(DateWindow):
    magnet_id: int | None = None
    source: str | None = None
    medium: str | None = None
    status: str | None = None
    search: str | None = None


class TouchFilter(DateWindow):
    code: str | None = None
    code_status: str | None = None
    magnet_id: int | None = None
    bitrix_status: str | None = None


async def list_magnets(session: AsyncSession) -> list[Row[tuple[LeadMagnet, int, int]]]:
    links = select(func.count()).where(AttributionLink.lead_magnet_id == LeadMagnet.id)
    delivered = select(func.count()).where(
        Touch.lead_magnet_id == LeadMagnet.id,
        Touch.magnet_delivered.is_(True),
        Touch.created_at >= utcnow() - timedelta(days=30),
    )
    return list(
        (
            await session.execute(
                select(LeadMagnet, links.scalar_subquery(), delivered.scalar_subquery()).order_by(
                    LeadMagnet.sort, LeadMagnet.id
                )
            )
        ).all()
    )


async def list_dict(
    session: AsyncSession,
    kind: Dictionary,
    *,
    only_active: bool = False,
) -> list[DictValue]:
    stmt = select(DictValue).where(DictValue.dict == kind).order_by(DictValue.sort, DictValue.id)
    if only_active:
        stmt = stmt.where(DictValue.is_active.is_(True))
    return list((await session.scalars(stmt)).all())


async def link_choices(
    session: AsyncSession,
) -> tuple[list[LeadMagnet], list[DictValue], list[DictValue], list[str]]:
    magnets = list((await session.scalars(active_magnets())).all())
    source = await list_dict(session, "source", only_active=True)
    medium = await list_dict(session, "medium", only_active=True)
    recent = list(
        (
            await session.scalars(
                select(AttributionLink.utm_campaign)
                .group_by(AttributionLink.utm_campaign)
                .order_by(func.max(AttributionLink.id).desc())
                .limit(5)
            )
        ).all()
    )
    return magnets, source, medium, recent


async def list_links(
    session: AsyncSession,
    filters: LinkFilter,
    zone: ZoneInfo,
    page: int,
) -> list[Row[tuple[AttributionLink, str, int, int, datetime | None]]]:
    stats = (
        select(
            Touch.link_id.label("link_id"),
            func.count().label("touch_count"),
            func.sum(Touch.is_new_user.cast(Integer)).label("new_count"),
            func.max(Touch.created_at).label("last_touch"),
        )
        .where(Touch.link_id.is_not(None))
        .group_by(Touch.link_id)
        .subquery()
    )
    stmt = (
        select(
            AttributionLink,
            LeadMagnet.name,
            func.coalesce(stats.c.touch_count, 0),
            func.coalesce(stats.c.new_count, 0),
            stats.c.last_touch,
        )
        .join(LeadMagnet, AttributionLink.lead_magnet_id == LeadMagnet.id)
        .outerjoin(
            stats,
            AttributionLink.id == stats.c.link_id,
        )
    )
    for column, value in (
        (AttributionLink.lead_magnet_id, filters.magnet_id),
        (AttributionLink.utm_source, filters.source),
        (AttributionLink.utm_medium, filters.medium),
        (AttributionLink.status, filters.status),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if filters.search:
        terms = [
            col.icontains(filters.search, autoescape=True)
            for col in (
                AttributionLink.code,
                AttributionLink.utm_campaign,
                AttributionLink.placement,
            )
        ]
        stmt = stmt.where(or_(*terms))
    if (lower := filters.lower(zone)) is not None:
        stmt = stmt.where(AttributionLink.created_at >= lower)
    if (upper := filters.upper(zone)) is not None:
        stmt = stmt.where(AttributionLink.created_at < upper)
    return list(
        (
            await session.execute(
                stmt.order_by(AttributionLink.id.desc())
                .offset((page - 1) * PAGE_SIZE)
                .limit(PAGE_SIZE + 1)
            )
        ).all()
    )


async def list_touches(
    session: AsyncSession,
    filters: TouchFilter,
    zone: ZoneInfo,
    page: int,
) -> list[tuple[Touch, str | None, str | None, str | None]]:
    stmt = (
        select(Touch, AttributionLink.code, LeadMagnet.name, User.username)
        .join(User, User.tg_id == Touch.tg_id)
        .outerjoin(AttributionLink, Touch.link_id == AttributionLink.id)
        .outerjoin(LeadMagnet, LeadMagnet.id == Touch.lead_magnet_id)
    )
    constraints = []
    for column, value in (
        (Touch.code_status, filters.code_status),
        (Touch.lead_magnet_id, filters.magnet_id),
        (Touch.bitrix_status, filters.bitrix_status),
    ):
        if value is not None:
            constraints.append(column == value)
    if filters.code:
        constraints.append(
            or_(
                AttributionLink.code == filters.code,
                and_(Touch.link_id.is_(None), Touch.raw_payload == filters.code),
            )
        )
    if (lower := filters.lower(zone)) is not None:
        constraints.append(Touch.created_at >= lower)
    if (upper := filters.upper(zone)) is not None:
        constraints.append(Touch.created_at < upper)
    result = await session.execute(
        stmt.where(*constraints)
        .order_by(Touch.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)
    )
    return [(touch, code, magnet, username) for touch, code, magnet, username in result]


async def list_filter_magnets(session: AsyncSession) -> list[LeadMagnet]:
    return list(
        (await session.scalars(select(LeadMagnet).order_by(LeadMagnet.sort, LeadMagnet.id))).all()
    )
