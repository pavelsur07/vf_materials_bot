from bot.core.config import Settings
from bot.integrations.telegram import TelegramChannelAdapter
from bot.modules.leads.dto import LeadNotificationIn


class NotifyLeadUseCase:
    """Relay a site lead notification into the configured leads chat or topic."""

    def __init__(self, settings: Settings, telegram: TelegramChannelAdapter) -> None:
        self._settings = settings
        self._telegram = telegram

    async def send(self, data: LeadNotificationIn) -> str | None:
        """Return None on success, otherwise a failure reason safe to show to the site."""
        sent = await self._telegram.send_message(
            chat_id=self._settings.leads_chat_id,
            thread_id=self._settings.leads_topic_id,
            text=data.text,
        )
        if not sent:
            return "telegram send failed"
        return None
