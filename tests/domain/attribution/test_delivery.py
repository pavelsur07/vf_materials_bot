from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import LeadMagnet, Touch, User


async def test_menu_choice_updates_original_touch_and_blocked_delivery(
    session: AsyncSession,
) -> None:
    from vashfindir.domain.attribution.dto import StartRequest
    from vashfindir.domain.attribution.touches import (
        finish_delivery,
        register_touch,
        select_magnet,
    )

    active = LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Текст")
    inactive = LeadMagnet(
        prefix="opiu",
        name="ОПиУ",
        content_type="text",
        message="Текст",
        is_active=False,
    )
    session.add_all([active, inactive])
    await session.commit()
    result = await register_touch(
        session, StartRequest(tg_id=765, first_name="Иван", payload="opiu_001")
    )
    assert await select_magnet(session, 456, result.touch_id, active.id) is None
    assert await select_magnet(session, 765, result.touch_id, inactive.id) is None
    choice = await select_magnet(session, 765, result.touch_id, active.id)
    assert choice is not None
    assert choice.prefix == "dds"
    await finish_delivery(session, 765, result.touch_id, delivered=False, blocked=True)
    touch = await session.get(Touch, result.touch_id)
    user = await session.get(User, 1)
    assert user is not None and user.is_blocked
    assert touch is not None
    assert (touch.lead_magnet_id, touch.magnet_source, touch.magnet_delivered) == (
        active.id,
        "menu",
        False,
    )
