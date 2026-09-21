from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.users import get_or_create_user


async def test_creates_new_user(session: AsyncSession) -> None:
    user = await get_or_create_user(session, tg_id=42, username="bob", first_name="Bob")
    assert user.id is not None
    assert user.tg_id == 42
    assert user.username == "bob"


async def test_returns_existing_and_updates_profile(session: AsyncSession) -> None:
    first = await get_or_create_user(session, tg_id=42, username="bob", first_name="Bob")
    second = await get_or_create_user(session, tg_id=42, username="bobby", first_name="Bobby")
    assert second.id == first.id
    assert second.username == "bobby"
    assert second.first_name == "Bobby"
