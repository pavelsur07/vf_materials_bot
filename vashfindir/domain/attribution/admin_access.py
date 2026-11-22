from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionAdminChallenge
from vashfindir.domain.attribution.settings import get_preferences
from vashfindir.domain.jobs import utcnow


def _digest(code: str) -> str:
    return sha256(code.encode()).hexdigest()


async def issue_challenge(session: AsyncSession) -> str:
    now = utcnow()
    code = token_urlsafe(24)
    await session.execute(
        delete(AttributionAdminChallenge).where(AttributionAdminChallenge.expires_at <= now)
    )
    session.add(
        AttributionAdminChallenge(digest=_digest(code), expires_at=now + timedelta(minutes=10))
    )
    return code


async def approve_challenge(
    session: AsyncSession,
    code: str,
    tg_id: int,
    bootstrap_admins: list[int],
) -> bool:
    preferences = await get_preferences(session, bootstrap_admins)
    if tg_id not in preferences.admin_ids or len(code) != 32:
        return False
    approved = await session.scalar(
        update(AttributionAdminChallenge)
        .where(
            AttributionAdminChallenge.digest == _digest(code),
            AttributionAdminChallenge.expires_at > utcnow(),
            AttributionAdminChallenge.approved_by.is_(None),
        )
        .values(approved_by=tg_id)
        .returning(AttributionAdminChallenge.approved_by)
    )
    return approved is not None


async def consume_challenge(
    session: AsyncSession,
    code: str,
    bootstrap_admins: list[int],
) -> int | None:
    tg_id = await session.scalar(
        delete(AttributionAdminChallenge)
        .where(
            AttributionAdminChallenge.digest == _digest(code),
            AttributionAdminChallenge.expires_at > utcnow(),
            AttributionAdminChallenge.approved_by.is_not(None),
        )
        .returning(AttributionAdminChallenge.approved_by)
    )
    preferences = await get_preferences(session, bootstrap_admins)
    return tg_id if tg_id in preferences.admin_ids else None
