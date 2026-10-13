from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from bot.core.config import Settings
from bot.integrations.telegram import TelegramChannelAdapter
from bot.modules.leads.dto import LeadNotificationIn
from bot.modules.leads.use_cases import NotifyLeadUseCase


@pytest.fixture
def use_case() -> NotifyLeadUseCase:
    adapter = TelegramChannelAdapter(AsyncMock(spec=Bot))
    settings = Settings(leads_chat_id=-1001, leads_topic_id=7)
    return NotifyLeadUseCase(settings, adapter)


async def test_send_relays_text_to_configured_topic(use_case: NotifyLeadUseCase) -> None:
    reason = await use_case.send(LeadNotificationIn(text="Новое обращение №17"))

    assert reason is None
    use_case._telegram._bot.send_message.assert_awaited_once_with(
        chat_id=-1001,
        message_thread_id=7,
        text="Новое обращение №17",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def test_send_returns_reason_when_telegram_fails(use_case: NotifyLeadUseCase) -> None:
    use_case._telegram._bot.send_message.side_effect = TelegramAPIError(
        method="sendMessage",
        message="boom",
    )

    reason = await use_case.send(LeadNotificationIn(text="lead"))

    assert reason == "telegram send failed"
