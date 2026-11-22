from typing import Literal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from vashfindir.domain.attribution.dto import MagnetContent
from vashfindir.modules.attribution.dialogs import CATALOG_BUTTON, CHECK_BUTTON, SUBSCRIBE_BUTTON


class AttributionAction(CallbackData, prefix="at"):
    action: Literal["catalog", "select", "gate"]
    touch_id: int
    magnet_id: int = 0


def catalog_button(touch_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=CATALOG_BUTTON,
        callback_data=AttributionAction(action="catalog", touch_id=touch_id).pack(),
    )


def catalog_kb(touch_id: int, magnets: list[MagnetContent]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for magnet in magnets:
        builder.button(
            text=magnet.name,
            callback_data=AttributionAction(
                action="select", touch_id=touch_id, magnet_id=magnet.id
            ),
        )
    builder.adjust(1)
    return builder.as_markup()


def subscribe_kb(channel_url: str, touch_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if channel_url:
        builder.button(text=SUBSCRIBE_BUTTON, url=channel_url)
    builder.button(
        text=CHECK_BUTTON, callback_data=AttributionAction(action="gate", touch_id=touch_id)
    )
    builder.adjust(1)
    return builder.as_markup()
