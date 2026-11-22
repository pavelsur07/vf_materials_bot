from sqlalchemy.ext.asyncio import AsyncSession


async def test_saved_allowlist_supersedes_bootstrap(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.settings import (
        AttributionPreferences,
        get_preferences,
        save_preferences,
    )

    async with session.begin():
        initial = await get_preferences(session, [123])
        assert initial.admin_ids == [123]
        assert initial.dedup_minutes == 10
        assert initial.timezone == "Europe/Moscow"
        await save_preferences(session, AttributionPreferences(admin_ids=[456]), [123], 123)
    assert (await get_preferences(session, [123])).admin_ids == [456]
