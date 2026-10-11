from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.modules.onboarding.use_cases import OnboardingUseCase


class DiMiddleware(BaseMiddleware):
    """Injects domain dependencies into aiogram handler data."""

    def __init__(self, onboarding_use_case: OnboardingUseCase) -> None:
        self._onboarding_use_case = onboarding_use_case

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["use_case"] = self._onboarding_use_case
        return await handler(event, data)
