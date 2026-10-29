import logging

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


class TelegramChannelAdapter:
    """Adapter for Telegram channel-related API calls."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, thread_id: int, text: str) -> bool:
        """Send a message to a chat or forum topic. False if Telegram API call fails."""
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id or None,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramAPIError as exc:
            logger.error("Failed to send message to chat %s: %s", chat_id, exc)
            return False
        return True

    async def get_member_status(self, channel_id: int, user_id: int) -> str | None:
        """Return chat member status or None if Telegram API call fails."""
        try:
            member = await self._bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        except TelegramAPIError as exc:
            logger.error(
                "Failed to get chat member for user %s in channel %s: %s",
                user_id,
                channel_id,
                exc,
            )
            return None
        return str(member.status)
