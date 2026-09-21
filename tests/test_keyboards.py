from bot.keyboards.main import MenuCb, main_menu_kb


def test_main_menu_callback_data_roundtrip() -> None:
    kb = main_menu_kb()
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 3
    for btn in buttons:
        assert btn.callback_data is not None
        cb = MenuCb.unpack(btn.callback_data)
        assert cb.section in {"materials", "consultation", "about"}
