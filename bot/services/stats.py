from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


async def count_users(session: AsyncSession) -> int:
    total = await session.scalar(select(func.count()).select_from(User))
    return total or 0


async def list_recent_users(session: AsyncSession, limit: int = 50) -> list[User]:
    result = await session.scalars(select(User).order_by(User.created_at.desc()).limit(limit))
    return list(result)
