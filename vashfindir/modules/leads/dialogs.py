from datetime import datetime

TEST_MESSAGES = {
    "ok": "Тестовое сообщение отправлено в чат уведомлений о лидах.",
    "disabled": (
        "Релей не настроен: задайте LEAD_API_TOKEN и LEADS_CHAT_ID в .env и перезапустите админку."
    ),
    "failed": (
        "Telegram отклонил сообщение. Проверьте, что бот добавлен в группу,"
        " а LEADS_CHAT_ID и LEADS_TOPIC_ID верны."
    ),
}


def test_message(now: datetime) -> str:
    return (
        "<b>Тестовое сообщение</b>\n\n"
        "Релей уведомлений о лидах работает.\n"
        f"Время (UTC): {now:%Y-%m-%d %H:%M:%S}"
    )
