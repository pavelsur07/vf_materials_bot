NOT_SUBSCRIBED_TEXT = (
    "Чтобы получить материал, подпишитесь на Telegram-канал «Ваш Финдир». "
    "После подписки вернитесь в бот и нажмите «Проверить подписку»."
)

SUBSCRIBED_TEXT_TEMPLATE = (
    "Подписка подтверждена. Ваш материал доступен по ссылке:\n{leadmagnet_url}"
)

NOT_SUBSCRIBED_AFTER_CHECK_TEXT = (
    "Подписка пока не найдена. Подпишитесь на канал и повторите проверку."
)

CHECK_ERROR_TEXT = "Не удалось проверить подписку. Попробуйте ещё раз."


def subscribed_text(leadmagnet_url: str) -> str:
    return SUBSCRIBED_TEXT_TEMPLATE.format(leadmagnet_url=leadmagnet_url)
