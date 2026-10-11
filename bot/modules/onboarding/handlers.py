import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.modules.onboarding.dto import OnboardingContext
from bot.modules.onboarding.keyboards import CheckSubCb, onboarding_kb
from bot.modules.onboarding.use_cases import OnboardingUseCase
from bot.services.subscription import SubscriptionStatus

router = Router(name="onboarding")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def on_start(
    message: Message,
    session: AsyncSession,
    use_case: OnboardingUseCase,
) -> None:
    if message.from_user is None:
        return

    user = message.from_user
    logger.info("User %s (%s) started bot", user.id, user.username)

    context = OnboardingContext(
        tg_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    result = await use_case.execute(session, context)

    await message.answer(result.text, reply_markup=onboarding_kb(result))
    if result.status == SubscriptionStatus.SUBSCRIBED:
        logger.info("Lead magnet access granted to user %s", user.id)


@router.callback_query(CheckSubCb.filter())
async def on_check_subscription(
    callback: CallbackQuery,
    callback_data: CheckSubCb,
    session: AsyncSession,
    use_case: OnboardingUseCase,
) -> None:
    if callback_data.action != "check" or callback.from_user is None:
        await callback.answer()
        return

    user = callback.from_user
    context = OnboardingContext(
        tg_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    result = await use_case.execute(session, context, is_retry=True)

    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(result.text, reply_markup=onboarding_kb(result))
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                logger.warning(
                    "Failed to edit message for user %s: %s",
                    callback.from_user.id,
                    exc,
                )
        except TelegramAPIError as exc:
            logger.warning(
                "Failed to edit message for user %s: %s",
                callback.from_user.id,
                exc,
            )

    if result.status == SubscriptionStatus.SUBSCRIBED:
        await callback.answer("Подписка подтверждена.")
        logger.info("Lead magnet access granted to user %s", callback.from_user.id)
    elif result.status == SubscriptionStatus.NOT_SUBSCRIBED:
        await callback.answer("Подписка пока не найдена.")
    else:
        await callback.answer("Не удалось проверить подписку.")
