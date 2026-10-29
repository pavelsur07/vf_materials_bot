from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.core.config import Settings
from vashfindir.domain.subscription import SubscriptionStatus
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.modules.onboarding.dto import OnboardingContext
from vashfindir.modules.onboarding.use_cases import OnboardingUseCase


@pytest.fixture
def use_case() -> OnboardingUseCase:
    settings = Settings(
        channel_id=100,
        channel_url="https://t.me/vashfindir",
        leadmagnet_url="https://example.com/lead",
    )
    telegram = AsyncMock(spec=TelegramChannelAdapter)
    return OnboardingUseCase(settings, telegram)


async def test_onboarding_subscribed(use_case: OnboardingUseCase, session: AsyncSession) -> None:
    use_case._telegram.get_member_status.return_value = "member"
    context = OnboardingContext(tg_id=42, username="bob", first_name="Bob")
    result = await use_case.execute(session, context)

    assert result.status == SubscriptionStatus.SUBSCRIBED
    assert "example.com/lead" in result.text
    assert result.leadmagnet_url == "https://example.com/lead"


async def test_onboarding_not_subscribed(
    use_case: OnboardingUseCase,
    session: AsyncSession,
) -> None:
    use_case._telegram.get_member_status.return_value = "left"
    context = OnboardingContext(tg_id=42, username="bob", first_name="Bob")
    result = await use_case.execute(session, context, is_retry=True)

    assert result.status == SubscriptionStatus.NOT_SUBSCRIBED
    assert result.is_retry is True


async def test_onboarding_check_error(
    use_case: OnboardingUseCase,
    session: AsyncSession,
) -> None:
    use_case._telegram.get_member_status.return_value = None
    context = OnboardingContext(tg_id=42, username="bob", first_name="Bob")
    result = await use_case.execute(session, context)

    assert result.status == SubscriptionStatus.CHECK_ERROR
