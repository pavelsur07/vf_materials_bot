from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.services.stats import count_users, list_recent_users


async def test_count_users_empty(session: AsyncSession) -> None:
    assert await count_users(session) == 0


async def test_stats_with_users(session: AsyncSession) -> None:
    session.add(User(tg_id=10, username="u1", first_name="User One"))
    session.add(User(tg_id=20, username="u2", first_name="User Two"))
    await session.commit()

    assert await count_users(session) == 2

    users = await list_recent_users(session)
    assert len(users) == 2
    assert {user.tg_id for user in users} == {10, 20}


async def test_list_recent_users_respects_limit(session: AsyncSession) -> None:
    for i in range(5):
        session.add(User(tg_id=100 + i))
    await session.commit()

    users = await list_recent_users(session, limit=3)
    assert len(users) == 3
