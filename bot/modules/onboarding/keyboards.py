from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.modules.onboarding.dto import OnboardingResult


class CheckSubCb(CallbackData, prefix="sub"):
    action: str


SUBSCRIBE_BUTTON_TEXT = "Подписаться на канал"
CHECK_BUTTON_TEXT = "Проверить подписку"
GET_MATERIAL_BUTTON_TEXT = "Получить материал"
RETRY_BUTTON_TEXT = "Повторить проверку"


def subscribe_kb(channel_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=SUBSCRIBE_BUTTON_TEXT, url=channel_url)
    builder.button(text=CHECK_BUTTON_TEXT, callback_data=CheckSubCb(action="check"))
    builder.adjust(1)
    return builder.as_markup()


def leadmagnet_kb(leadmagnet_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=GET_MATERIAL_BUTTON_TEXT, url=leadmagnet_url)
    return builder.as_markup()


def retry_check_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=RETRY_BUTTON_TEXT, callback_data=CheckSubCb(action="check"))
    return builder.as_markup()


def onboarding_kb(result: OnboardingResult) -> InlineKeyboardMarkup:
    from bot.services.subscription import SubscriptionStatus

    if result.status == SubscriptionStatus.SUBSCRIBED:
        return leadmagnet_kb(result.leadmagnet_url)
    if result.status == SubscriptionStatus.NOT_SUBSCRIBED:
        return subscribe_kb(result.channel_url)
    return retry_check_kb()
