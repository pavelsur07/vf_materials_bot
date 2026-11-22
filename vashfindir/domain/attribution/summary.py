from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import coalesce

from vashfindir.db.models import AttributionLink, AttributionSetting, Job, LeadMagnet, Touch
from vashfindir.domain.attribution.queries import utc_boundary
from vashfindir.domain.attribution.settings import get_preferences, get_setting, put_setting
from vashfindir.domain.jobs import JobStatus, enqueue_job

SUMMARY_JOB = "attribution_summary"
_SENT_DAY = "summary_sent_day"


class IssuedMagnet(BaseModel):
    name: str
    count: int


class EmptyLink(BaseModel):
    code: str
    placement: str


class DailySummary(BaseModel):
    day: date
    total: int
    new_users: int
    direct: int
    unknown: int
    errors: int
    direct_unknown_percent: float
    magnets: list[IssuedMagnet]
    empty_links: list[EmptyLink]


def _sum_if(condition: ColumnElement[bool]) -> coalesce[int]:
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


async def build_summary(session: AsyncSession, day: date, zone: ZoneInfo) -> DailySummary:
    begin = utc_boundary(day, zone)
    end = utc_boundary(day + timedelta(days=1), zone)
    production = Touch.is_test.is_(False)
    day_filter = (production, Touch.created_at >= begin, Touch.created_at < end)
    counts = await session.execute(
        select(
            func.count(Touch.id),
            _sum_if(Touch.is_new_user.is_(True)),
            _sum_if(Touch.code_status == "direct"),
            _sum_if(Touch.code_status == "unknown"),
            _sum_if(Touch.bitrix_status == "error"),
        ).where(*day_filter)
    )
    total, new_users, direct, unknown, errors = counts.one()
    magnets = await session.execute(
        select(LeadMagnet.name, func.count(Touch.id))
        .join(Touch, Touch.lead_magnet_id == LeadMagnet.id)
        .where(*day_filter, Touch.magnet_delivered.is_(True))
        .group_by(LeadMagnet.id)
        .order_by(LeadMagnet.sort, LeadMagnet.id)
    )

    week_begin = utc_boundary(day - timedelta(days=6), zone)
    week = await session.execute(
        select(
            func.count(Touch.id),
            _sum_if(Touch.code_status.in_(["direct", "unknown"])),
        ).where(production, Touch.created_at >= week_begin, Touch.created_at < end)
    )
    week_total, unattributed = week.one()

    links = (
        await session.scalars(
            select(AttributionLink)
            .where(
                AttributionLink.status == "active",
                AttributionLink.period_start <= day - timedelta(days=6),
            )
            .order_by(AttributionLink.id)
        )
    ).all()
    empty: list[EmptyLink] = []
    for link in links:
        if link.period_start is None:
            continue
        window_start = utc_boundary(link.period_start, zone)
        window_end = utc_boundary(link.period_start + timedelta(days=7), zone)
        matched = await session.scalar(
            select(Touch.id)
            .where(
                production,
                Touch.link_id == link.id,
                Touch.created_at >= window_start,
                Touch.created_at < window_end,
            )
            .limit(1)
        )
        if matched is None:
            empty.append(EmptyLink(code=link.code, placement=link.placement))
    return DailySummary(
        day=day,
        total=total,
        new_users=new_users,
        direct=direct,
        unknown=unknown,
        errors=errors,
        magnets=[IssuedMagnet(name=name, count=count) for name, count in magnets],
        empty_links=empty,
        direct_unknown_percent=100 * unattributed / week_total if week_total else 0,
    )


def local_datetime(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(zone)


async def enqueue_daily_summary(
    session: AsyncSession,
    bootstrap_admins: list[int],
    now: datetime,
) -> bool:
    prefs = await get_preferences(session, bootstrap_admins)
    if not prefs.service_chat_id:
        return False
    local = local_datetime(now, ZoneInfo(prefs.timezone))
    if local.time() < prefs.summary_time:
        return False
    scheduled_day = local.date().isoformat()
    await session.execute(
        update(AttributionSetting)
        .where(
            AttributionSetting.key == _SENT_DAY,
        )
        .values(value=AttributionSetting.value)
    )
    if await get_setting(session, _SENT_DAY) == scheduled_day:
        return False
    recent = await session.scalar(
        select(Job.id)
        .where(
            Job.type == SUMMARY_JOB,
            func.json_extract(Job.payload, "$.day") == scheduled_day,
            (Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
            | (Job.created_at > now - timedelta(minutes=5)),
        )
        .limit(1)
    )
    if recent is not None:
        return False
    await enqueue_job(session, SUMMARY_JOB, {"day": scheduled_day}, run_at=now)
    return True


async def mark_summary_sent(session: AsyncSession, scheduled_day: date) -> None:
    await put_setting(session, _SENT_DAY, scheduled_day.isoformat())


async def summary_is_sent(session: AsyncSession, scheduled_day: date) -> bool:
    return await get_setting(session, _SENT_DAY) == scheduled_day.isoformat()
