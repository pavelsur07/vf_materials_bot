from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import Integer, case, cast, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from vashfindir.db.models import AttributionLink, Job, LeadMagnet, Touch, User
from vashfindir.domain.attribution.dto import UTM_FIELDS
from vashfindir.domain.jobs import JobStatus, enqueue_job, utcnow

BITRIX_JOB = "attribution_bitrix"
_RETRY_MINUTES = (1, 5, 15, 60, 240)
_RECOVER_DELIVERY_AFTER = timedelta(minutes=2)


class BitrixWork(BaseModel):
    touch_id: int
    tg_id: int
    first_touch_id: int
    first_name: str
    last_name: str
    username: str
    is_test: bool
    lead_id: int | None
    first_code: str
    last_code: str
    current_code: str
    current_at: datetime
    first_magnet: str | None
    current_magnet: str | None
    delivered_magnets: str
    first_utm: dict[str, str | None]
    attempts: int
    comment_id: int | None
    magnet_delivered: bool


async def enqueue_due_touches(session: AsyncSession, now: datetime) -> int:
    # Serialize reconciliation across contenders before evaluating the active jobs.
    await session.execute(update(Touch).where(Touch.id == -1).values(id=Touch.id))
    older = aliased(Touch)
    already_queued = exists(
        select(Job.id).where(
            Job.type == BITRIX_JOB,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            cast(func.json_extract(Job.payload, "$.touch_id"), Integer) == Touch.id,
        )
    )
    awaiting_older = exists(
        select(older.id).where(
            older.tg_id == Touch.tg_id,
            older.id < Touch.id,
            older.bitrix_status == "pending",
        )
    )
    candidates = (
        await session.scalars(
            select(Touch.id)
            .where(
                Touch.bitrix_status == "pending",
                or_(
                    Touch.delivery_finished.is_(True),
                    Touch.created_at <= now - _RECOVER_DELIVERY_AFTER,
                ),
                or_(Touch.bitrix_next_attempt_at.is_(None), Touch.bitrix_next_attempt_at <= now),
                ~already_queued,
                ~awaiting_older,
            )
            .order_by(Touch.id)
            .limit(100)
        )
    ).all()
    for touch_id in candidates:
        await enqueue_job(session, BITRIX_JOB, {"touch_id": touch_id}, run_at=now)
    return len(candidates)


async def _touch_code(session: AsyncSession, row: Touch) -> str:
    if row.code_status == "direct":
        return "direct"
    if row.link_id is not None:
        link = await session.get(AttributionLink, row.link_id)
        if link is not None:
            return link.code
    return f"unknown:{row.raw_payload or ''}"


async def _magnet_name(session: AsyncSession, row: Touch) -> str | None:
    if row.lead_magnet_id is None:
        return None
    magnet = await session.get(LeadMagnet, row.lead_magnet_id)
    return magnet.name if magnet else None


async def get_work(session: AsyncSession, touch_id: int, now: datetime) -> BitrixWork | None:
    touch = await session.get(Touch, touch_id)
    if (
        touch is None
        or touch.bitrix_status != "pending"
        or (touch.bitrix_next_attempt_at and touch.bitrix_next_attempt_at > now)
    ):
        return None
    user = await session.scalar(select(User).where(User.tg_id == touch.tg_id))
    if user is None or user.first_touch_id is None or user.last_touch_id is None:
        return None
    first = await session.get(Touch, user.first_touch_id)
    last = await session.get(Touch, user.last_touch_id)
    if first is None or last is None:
        return None
    prefixes = (
        await session.scalars(
            select(LeadMagnet.prefix)
            .join(Touch, Touch.lead_magnet_id == LeadMagnet.id)
            .where(
                Touch.tg_id == user.tg_id,
                Touch.magnet_delivered.is_(True),
                Touch.is_test == touch.is_test,
            )
            .group_by(LeadMagnet.id)
            .order_by(func.min(Touch.id))
        )
    ).all()
    return BitrixWork(
        touch_id=touch.id,
        tg_id=user.tg_id,
        first_touch_id=first.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=f"@{user.username}" if user.username else "",
        is_test=touch.is_test,
        lead_id=user.bitrix_lead_id,
        first_code=await _touch_code(session, first),
        last_code=await _touch_code(session, last),
        current_code=await _touch_code(session, touch),
        current_at=touch.created_at,
        first_magnet=await _magnet_name(session, first),
        current_magnet=await _magnet_name(session, touch),
        delivered_magnets=", ".join(prefixes),
        first_utm={field.upper(): getattr(first, field) for field in UTM_FIELDS},
        attempts=touch.bitrix_attempts,
        comment_id=touch.bitrix_comment_id,
        magnet_delivered=touch.magnet_delivered,
    )


async def save_lead_id(session: AsyncSession, tg_id: int, lead_id: int) -> None:
    await session.execute(update(User).where(User.tg_id == tg_id).values(bitrix_lead_id=lead_id))


async def start_comment(session: AsyncSession, touch_id: int) -> None:
    # Bitrix24 IDs are positive, so zero denotes a comment request in flight.
    await session.execute(update(Touch).where(Touch.id == touch_id).values(bitrix_comment_id=0))


async def succeed_touch(
    session: AsyncSession,
    work: BitrixWork,
    comment_id: int | None,
) -> None:
    delivery_changed = Touch.magnet_delivered.is_(True) & (not work.magnet_delivered)
    await session.execute(
        update(Touch)
        .where(Touch.id == work.touch_id)
        .values(
            bitrix_status=case((delivery_changed, "pending"), else_="ok"),
            bitrix_attempts=case((delivery_changed, 0), else_=work.attempts + 1),
            bitrix_next_attempt_at=None,
            bitrix_error=None,
            bitrix_comment_id=comment_id,
        )
    )


async def fail_touch(
    session: AsyncSession,
    work: BitrixWork,
    error: str,
    retry_after: int,
    now: datetime,
) -> bool:
    exhausted = work.attempts >= len(_RETRY_MINUTES)
    next_attempt = None
    if not exhausted:
        next_attempt = now + max(
            timedelta(minutes=_RETRY_MINUTES[work.attempts]),
            timedelta(seconds=retry_after),
        )
    await session.execute(
        update(Touch)
        .where(Touch.id == work.touch_id)
        .values(
            bitrix_status="error" if exhausted else "pending",
            bitrix_error=error,
            bitrix_next_attempt_at=next_attempt,
            bitrix_attempts=work.attempts + 1,
        )
    )
    return exhausted


async def retry_errors(session: AsyncSession, touch_id: int | None = None) -> int:
    statement = update(Touch).where(Touch.bitrix_status == "error")
    if touch_id is not None:
        statement = statement.where(Touch.id == touch_id)
    result = await session.scalars(
        statement.values(
            bitrix_status="pending",
            bitrix_attempts=0,
            bitrix_next_attempt_at=utcnow(),
            bitrix_error=None,
        ).returning(Touch.id)
    )
    return len(result.all())
