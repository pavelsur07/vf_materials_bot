import csv
from codecs import BOM_UTF8
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, date, datetime
from io import StringIO
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, LeadMagnet, Touch, User
from vashfindir.domain.attribution.dto import UTM_FIELDS
from vashfindir.domain.attribution.queries import DateWindow

_LINK_HEADERS = (
    "code",
    "magnet_prefix",
    "magnet_name",
    *UTM_FIELDS,
    "placement",
    "period_start",
    "period_end",
    "budget",
    "status",
    "created_at",
)
_TOUCH_HEADERS = (
    "touch_id",
    "created_at",
    "tg_id",
    "username",
    "code",
    "raw_payload",
    "code_status",
    "magnet_prefix",
    "magnet_source",
    *UTM_FIELDS,
    "is_new_user",
    "magnet_delivered",
    "bitrix_lead_id",
)


class CSVRows:
    def __init__(self) -> None:
        self._buffer = StringIO(newline="")
        self._writer = csv.writer(self._buffer)

    def encode(self, values: Iterable[object]) -> bytes:
        self._buffer.seek(0)
        self._buffer.truncate()
        self._writer.writerow(values)
        return self._buffer.getvalue().encode("utf-8")


def _date_string(day: date | None) -> str:
    return f"{day.isoformat()} 00:00:00" if day else ""


def _timestamp(value: datetime, zone: ZoneInfo) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S")


async def export_links(
    session: AsyncSession,
    period: DateWindow,
    zone: ZoneInfo,
) -> AsyncIterator[bytes]:
    query = (
        select(AttributionLink, LeadMagnet.prefix, LeadMagnet.name)
        .join(LeadMagnet, LeadMagnet.id == AttributionLink.lead_magnet_id)
        .order_by(AttributionLink.id)
    )
    if (lower := period.lower(zone)) is not None:
        query = query.where(AttributionLink.created_at >= lower)
    if (upper := period.upper(zone)) is not None:
        query = query.where(AttributionLink.created_at < upper)
    rows = CSVRows()
    result = await session.stream(query.execution_options(yield_per=500))
    try:
        yield BOM_UTF8 + rows.encode(_LINK_HEADERS)
        async for link, prefix, name in result:
            yield rows.encode(
                (
                    link.code,
                    prefix,
                    name,
                    *(getattr(link, field) for field in UTM_FIELDS),
                    link.placement,
                    _date_string(link.period_start),
                    _date_string(link.period_end),
                    link.budget,
                    link.status,
                    _timestamp(link.created_at, zone),
                )
            )
    finally:
        await result.close()


async def export_touches(
    session: AsyncSession,
    period: DateWindow,
    zone: ZoneInfo,
    *,
    include_test: bool = False,
) -> AsyncIterator[bytes]:
    query = select(
        Touch, AttributionLink.code, LeadMagnet.prefix, User.username, User.bitrix_lead_id
    )
    query = (
        query.join(User, User.tg_id == Touch.tg_id)
        .outerjoin(AttributionLink, AttributionLink.id == Touch.link_id)
        .outerjoin(LeadMagnet, LeadMagnet.id == Touch.lead_magnet_id)
        .order_by(Touch.id)
    )
    if not include_test:
        query = query.where(Touch.is_test.is_(False))
    if (lower := period.lower(zone)) is not None:
        query = query.where(Touch.created_at >= lower)
    if (upper := period.upper(zone)) is not None:
        query = query.where(Touch.created_at < upper)
    rows = CSVRows()
    result = await session.stream(query.execution_options(yield_per=500))
    try:
        yield BOM_UTF8 + rows.encode(_TOUCH_HEADERS)
        async for touch, code, prefix, username, lead_id in result:
            yield rows.encode(
                (
                    touch.id,
                    _timestamp(touch.created_at, zone),
                    touch.tg_id,
                    username,
                    code or touch.code_status,
                    touch.raw_payload,
                    touch.code_status,
                    prefix,
                    touch.magnet_source,
                    *(getattr(touch, field) for field in UTM_FIELDS),
                    int(touch.is_new_user),
                    int(touch.magnet_delivered),
                    lead_id,
                )
            )
    finally:
        await result.close()
