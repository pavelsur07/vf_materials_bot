from aiogram import Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.domain.attribution.dto import MagnetContent, StartResult
from vashfindir.domain.attribution.touches import finish_delivery, get_touch, select_magnet
from vashfindir.modules.attribution.dialogs import (
    CATALOG_EXPIRED,
    DELIVERY_ERROR,
    MAGNET_UNAVAILABLE,
    NO_MAGNETS,
    SUBSCRIBE_TO_RECEIVE,
)
from vashfindir.modules.attribution.keyboards import AttributionAction, catalog_kb, subscribe_kb
from vashfindir.modules.attribution.use_cases import AttributionUseCase

router = Router(name="attribution")


async def show_catalogue(
    message: Message,
    tg_id: int,
    touch: StartResult,
    session: AsyncSession,
    attribution: AttributionUseCase,
) -> None:
    catalogue = await attribution.catalogue(session)
    await message.answer(
        catalogue.greeting if catalogue.magnets else f"{catalogue.greeting}\n\n{NO_MAGNETS}",
        parse_mode=None,
        reply_markup=catalog_kb(touch.touch_id, catalogue.magnets) if catalogue.magnets else None,
    )
    await finish_delivery(session, tg_id, touch.touch_id)


async def send_selected(
    message: Message,
    tg_id: int,
    touch_id: int,
    magnet: MagnetContent,
    session: AsyncSession,
    attribution: AttributionUseCase,
) -> None:
    if not await attribution.check_subscription(tg_id):
        await message.answer(
            SUBSCRIBE_TO_RECEIVE,
            reply_markup=subscribe_kb(attribution.settings.channel_url, touch_id),
        )
        await finish_delivery(session, tg_id, touch_id)
        return

    outcome = await attribution.deliver(session, tg_id, message.chat.id, touch_id, magnet)
    if outcome.status not in ("sent", "blocked"):
        await message.answer(DELIVERY_ERROR)


@router.callback_query(AttributionAction.filter())
async def on_attribution_action(
    callback: CallbackQuery,
    callback_data: AttributionAction,
    session: AsyncSession,
    attribution: AttributionUseCase,
) -> None:
    if not isinstance(callback.message, Message) or not attribution.settings.attribution_enabled:
        await callback.answer(CATALOG_EXPIRED)
        return
    tg_id = callback.from_user.id
    touch = await get_touch(session, tg_id, callback_data.touch_id)
    if touch is None:
        await callback.answer(CATALOG_EXPIRED)
        return

    if callback_data.action == "catalog":
        await callback.answer()
        await show_catalogue(callback.message, tg_id, touch, session, attribution)
        return

    magnet = touch.magnet
    if callback_data.action == "select":
        magnet = await select_magnet(session, tg_id, touch.touch_id, callback_data.magnet_id)
    if magnet is None:
        await callback.answer(MAGNET_UNAVAILABLE)
        return
    await callback.answer()
    await send_selected(callback.message, tg_id, touch.touch_id, magnet, session, attribution)
