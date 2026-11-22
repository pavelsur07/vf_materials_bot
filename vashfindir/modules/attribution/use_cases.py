from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.core.config import Settings
from vashfindir.domain.attribution.catalog import active_magnets
from vashfindir.domain.attribution.dto import MagnetContent, StartRequest, StartResult
from vashfindir.domain.attribution.settings import get_preferences
from vashfindir.domain.attribution.touches import finish_delivery, register_touch
from vashfindir.domain.subscription import SubscriptionStatus, classify_member_status
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.integrations.telegram_delivery import DeliveryResult, TelegramDelivery


class Catalogue(BaseModel):
    greeting: str
    magnets: list[MagnetContent]


class AttributionUseCase:
    def __init__(
        self,
        settings: Settings,
        telegram: TelegramChannelAdapter,
        delivery: TelegramDelivery,
    ) -> None:
        self.settings = settings
        self._telegram = telegram
        self._delivery = delivery

    async def register(self, session: AsyncSession, data: StartRequest) -> StartResult:
        async with session.begin():
            preferences = await get_preferences(
                session, self.settings.attribution_bootstrap_admin_tg_ids
            )
        return await register_touch(session, data, preferences)

    async def catalogue(self, session: AsyncSession) -> Catalogue:
        async with session.begin():
            preferences = await get_preferences(
                session, self.settings.attribution_bootstrap_admin_tg_ids
            )
            magnets = [
                MagnetContent.model_validate(magnet)
                for magnet in (await session.scalars(active_magnets())).all()
            ]
            return Catalogue(greeting=preferences.greeting, magnets=magnets)

    async def check_subscription(self, tg_id: int) -> bool:
        status = await self._telegram.get_member_status(self.settings.channel_id, tg_id)
        return classify_member_status(status) == SubscriptionStatus.SUBSCRIBED

    async def deliver(
        self,
        session: AsyncSession,
        tg_id: int,
        chat_id: int,
        touch_id: int,
        magnet: MagnetContent,
    ) -> DeliveryResult:
        outcome = await self._delivery.send_magnet(chat_id, magnet)
        await finish_delivery(
            session,
            tg_id,
            touch_id,
            delivered=outcome.status == "sent",
            blocked=outcome.status == "blocked",
        )
        return outcome
