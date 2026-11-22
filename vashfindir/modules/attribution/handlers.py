from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.domain.attribution.admin_access import approve_challenge
from vashfindir.domain.attribution.dto import MagnetContent, StartResult
from vashfindir.domain.attribution.touches import finish_delivery, get_touch, select_magnet
from vashfindir.modules.attribution.dialogs import (
    ADMIN_AUTH_FAILED,
    ADMIN_AUTH_OK,
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
        catalogue.greeting,
        parse_mode=None,
        reply_markup=catalog_kb(touch.touch_id, catalogue.magnets) if catalogue.magnets else None,
    )
    if not catalogue.magnets:
        await message.answer(NO_MAGNETS, parse_mode=None)
    await finish_delivery(session, tg_id, touch.touch_id)


async def send_selected(
    message: Message,
    tg_id: int,
    touch_id: int,
    magnet: MagnetContent,
    session: AsyncSession,
    attribution: AttributionUseCase,
) -> bool:
    if not await attribution.check_subscription(tg_id):
        await message.answer(
            SUBSCRIBE_TO_RECEIVE,
            reply_markup=subscribe_kb(attribution.settings.channel_url, touch_id),
        )
        await finish_delivery(session, tg_id, touch_id)
        return False

    outcome = await attribution.deliver(session, tg_id, message.chat.id, touch_id, magnet)
    if outcome.status not in ("sent", "blocked"):
        await message.answer(DELIVERY_ERROR)
    return outcome.status == "sent"


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


@router.message(Command("admin_auth"), F.chat.type == "private")
async def on_admin_auth(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    attribution: AttributionUseCase,
) -> None:
    if not attribution.settings.attribution_enabled or message.from_user is None:
        return
    async with session.begin():
        approved = await approve_challenge(
            session,
            command.args or "",
            message.from_user.id,
            attribution.settings.attribution_bootstrap_admin_tg_ids,
        )
    await message.answer(ADMIN_AUTH_OK if approved else ADMIN_AUTH_FAILED, parse_mode=None)
