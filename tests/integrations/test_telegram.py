from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatMemberMember, User

from bot.integrations.telegram import TelegramChannelAdapter


@pytest.fixture
def adapter() -> TelegramChannelAdapter:
    bot = AsyncMock(spec=Bot)
    return TelegramChannelAdapter(bot)


async def test_get_member_status_returns_status(adapter: TelegramChannelAdapter) -> None:
    adapter._bot.get_chat_member.return_value = ChatMemberMember(
        user=User(id=1, is_bot=False, first_name="Test"),
        status="member",
    )
    status = await adapter.get_member_status(channel_id=100, user_id=1)
    assert status == "member"
    adapter._bot.get_chat_member.assert_awaited_once_with(chat_id=100, user_id=1)


async def test_get_member_status_returns_none_on_api_error(
    adapter: TelegramChannelAdapter,
) -> None:
    adapter._bot.get_chat_member.side_effect = TelegramAPIError(
        method="getChatMember",
        message="test error",
    )
    status = await adapter.get_member_status(channel_id=100, user_id=1)
    assert status is None
