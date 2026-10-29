from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.core.config import Settings
from vashfindir.domain.subscription import SubscriptionStatus, classify_member_status
from vashfindir.domain.users import get_or_create_user
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.modules.onboarding.dialogs import (
    CHECK_ERROR_TEXT,
    NOT_SUBSCRIBED_AFTER_CHECK_TEXT,
    NOT_SUBSCRIBED_TEXT,
    subscribed_text,
)

from .dto import OnboardingContext, OnboardingResult


class OnboardingUseCase:
    """Onboarding scenario: save user and check channel subscription."""

    def __init__(
        self,
        settings: Settings,
        telegram_adapter: TelegramChannelAdapter,
    ) -> None:
        self._settings = settings
        self._telegram = telegram_adapter

    async def execute(
        self,
        session: AsyncSession,
        context: OnboardingContext,
        *,
        is_retry: bool = False,
    ) -> OnboardingResult:
        await get_or_create_user(
            session,
            tg_id=context.tg_id,
            username=context.username,
            first_name=context.first_name,
        )

        raw_status = await self._telegram.get_member_status(
            self._settings.channel_id,
            context.tg_id,
        )
        status = classify_member_status(raw_status)
        text = self._build_text(status, is_retry=is_retry)

        return OnboardingResult(
            status=status,
            text=text,
            channel_url=self._settings.channel_url,
            leadmagnet_url=self._settings.leadmagnet_url,
            is_retry=is_retry,
        )

    def _build_text(self, status: SubscriptionStatus, *, is_retry: bool) -> str:
        if status == SubscriptionStatus.SUBSCRIBED:
            return subscribed_text(self._settings.leadmagnet_url)
        if status == SubscriptionStatus.NOT_SUBSCRIBED:
            return NOT_SUBSCRIBED_AFTER_CHECK_TEXT if is_retry else NOT_SUBSCRIBED_TEXT
        return CHECK_ERROR_TEXT
