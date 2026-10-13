from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.enums import ParseMode
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


async def test_send_message_posts_html_to_topic(adapter: TelegramChannelAdapter) -> None:
    sent = await adapter.send_message(chat_id=-1001, thread_id=5, text="hello")

    assert sent is True
    adapter._bot.send_message.assert_awaited_once_with(
        chat_id=-1001,
        message_thread_id=5,
        text="hello",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def test_send_message_omits_thread_id_when_zero(adapter: TelegramChannelAdapter) -> None:
    sent = await adapter.send_message(chat_id=-1001, thread_id=0, text="hello")

    assert sent is True
    assert adapter._bot.send_message.await_args.kwargs["message_thread_id"] is None


async def test_send_message_returns_false_on_api_error(adapter: TelegramChannelAdapter) -> None:
    adapter._bot.send_message.side_effect = TelegramAPIError(
        method="sendMessage",
        message="test error",
    )

    sent = await adapter.send_message(chat_id=-1001, thread_id=0, text="hello")

    assert sent is False
