from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vashfindir.apps.bot import __main__ as main
from vashfindir.core.config import Settings
from vashfindir.db.models import LeadMagnet, Touch
from vashfindir.modules.attribution.keyboards import catalog_button
from vashfindir.modules.onboarding.keyboards import CheckSubCb, subscribe_kb


async def test_dispatcher_tracks_start_and_preserves_legacy_material(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Checklist"))
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    monkeypatch.setattr(main, "create_session_factory", lambda: factory)
    bot = Bot("12345:test-token")
    transport = AsyncMock()
    monkeypatch.setattr(bot.session, "make_request", transport)
    transport.side_effect = lambda _, method, **kwargs: (
        type("Member", (), {"status": "member"})()
        if method.__class__.__name__ == "GetChatMember"
        else True
    )

    settings = Settings(
        _env_file=None,
        attribution_enabled=True,
        leadmagnet_url="https://example.org/legacy",
        TELEGRAM_CHANNEL_ID=-1234,
        TELEGRAM_CHANNEL_URL="https://t.me/example",
    )
    dispatcher = main.build_dispatcher(bot, settings)
    try:
        for update_id, text in enumerate(("/start", "/start dds_999"), start=1):
            await dispatcher.feed_update(
                bot,
                Update(
                    update_id=update_id,
                    message=Message(
                        message_id=update_id,
                        date=datetime.now(UTC),
                        chat=Chat(id=765, type="private"),
                        text=text,
                        from_user=TelegramUser(id=765, is_bot=False, first_name="Иван"),
                    ),
                ),
            )
        user = TelegramUser(id=765, is_bot=False, first_name="Иван")
        markup = subscribe_kb("https://t.me/example")
        markup.inline_keyboard.append([catalog_button(1)])
        await dispatcher.feed_update(
            bot,
            Update(
                update_id=3,
                callback_query=CallbackQuery(
                    id="check",
                    from_user=user,
                    chat_instance="private",
                    data=CheckSubCb(action="check").pack(),
                    message=Message(
                        message_id=1,
                        date=datetime.now(UTC),
                        chat=Chat(id=765, type="private"),
                        reply_markup=markup,
                    ),
                ),
            ),
        )
        await dispatcher.feed_update(
            bot,
            Update(
                update_id=4,
                message=Message(
                    message_id=4,
                    date=datetime.now(UTC),
                    chat=Chat(id=-999, type="group"),
                    text="/start dds_894",
                    from_user=user,
                ),
            ),
        )
    finally:
        await bot.session.close()

    sent = [
        call.args[1]
        for call in transport.await_args_list
        if call.args[1].__class__.__name__ == "SendMessage"
    ]
    assert len(sent) == 3
    assert "https://example.org/legacy" in sent[0].text
    assert sent[0].reply_markup.inline_keyboard[-1][0].text == "Другие материалы"
    assert sent[1].text == "Checklist"
    assert "личный чат" in sent[2].text
    edits = [
        call.args[1]
        for call in transport.await_args_list
        if call.args[1].__class__.__name__ == "EditMessageText"
    ]
    assert edits[0].reply_markup.inline_keyboard[-1][0].text == "Другие материалы"
    touches = (await session.scalars(select(Touch).order_by(Touch.id))).all()
    assert [(touch.code_status, touch.magnet_delivered) for touch in touches] == [
        ("direct", False),
        ("unknown", True),
        ("unknown", False),
    ]
