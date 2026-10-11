from bot.modules.onboarding.keyboards import (
    CHECK_BUTTON_TEXT,
    GET_MATERIAL_BUTTON_TEXT,
    RETRY_BUTTON_TEXT,
    SUBSCRIBE_BUTTON_TEXT,
    CheckSubCb,
    leadmagnet_kb,
    onboarding_kb,
    retry_check_kb,
    subscribe_kb,
)


def _get_buttons(kb) -> list:
    return [btn for row in kb.inline_keyboard for btn in row]


def test_subscribe_kb() -> None:
    kb = subscribe_kb("https://t.me/vashfindir")
    buttons = _get_buttons(kb)
    assert len(buttons) == 2

    assert buttons[0].text == SUBSCRIBE_BUTTON_TEXT
    assert buttons[0].url == "https://t.me/vashfindir"

    assert buttons[1].text == CHECK_BUTTON_TEXT
    assert buttons[1].callback_data is not None
    cb = CheckSubCb.unpack(buttons[1].callback_data)
    assert cb.action == "check"


def test_leadmagnet_kb() -> None:
    kb = leadmagnet_kb("https://example.com/lead")
    buttons = _get_buttons(kb)
    assert len(buttons) == 1
    assert buttons[0].text == GET_MATERIAL_BUTTON_TEXT
    assert buttons[0].url == "https://example.com/lead"


def test_retry_check_kb() -> None:
    kb = retry_check_kb()
    buttons = _get_buttons(kb)
    assert len(buttons) == 1
    assert buttons[0].text == RETRY_BUTTON_TEXT
    assert buttons[0].callback_data is not None
    cb = CheckSubCb.unpack(buttons[0].callback_data)
    assert cb.action == "check"


def test_onboarding_kb_subscribed() -> None:
    from bot.modules.onboarding.dto import OnboardingResult
    from bot.services.subscription import SubscriptionStatus

    result = OnboardingResult(
        status=SubscriptionStatus.SUBSCRIBED,
        text="",
        channel_url="https://t.me/vashfindir",
        leadmagnet_url="https://example.com/lead",
        is_retry=False,
    )
    kb = onboarding_kb(result)
    buttons = _get_buttons(kb)
    assert len(buttons) == 1
    assert buttons[0].url == "https://example.com/lead"


def test_onboarding_kb_not_subscribed() -> None:
    from bot.modules.onboarding.dto import OnboardingResult
    from bot.services.subscription import SubscriptionStatus

    result = OnboardingResult(
        status=SubscriptionStatus.NOT_SUBSCRIBED,
        text="",
        channel_url="https://t.me/vashfindir",
        leadmagnet_url="https://example.com/lead",
        is_retry=False,
    )
    kb = onboarding_kb(result)
    buttons = _get_buttons(kb)
    assert len(buttons) == 2
    assert buttons[0].url == "https://t.me/vashfindir"


def test_onboarding_kb_check_error() -> None:
    from bot.modules.onboarding.dto import OnboardingResult
    from bot.services.subscription import SubscriptionStatus

    result = OnboardingResult(
        status=SubscriptionStatus.CHECK_ERROR,
        text="",
        channel_url="https://t.me/vashfindir",
        leadmagnet_url="https://example.com/lead",
        is_retry=True,
    )
    kb = onboarding_kb(result)
    buttons = _get_buttons(kb)
    assert len(buttons) == 1
    assert buttons[0].text == RETRY_BUTTON_TEXT
