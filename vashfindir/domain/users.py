from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import User


async def get_or_create_user(
    session: AsyncSession,
    *,
    tg_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(tg_id=tg_id, username=username, first_name=first_name)
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
    await session.commit()
    return user
