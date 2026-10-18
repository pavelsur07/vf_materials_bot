import logging

import uvicorn
from aiogram import Bot

from bot.api.app import create_api_app
from bot.core.config import get_settings
from bot.core.glitchtip import init_glitchtip
from bot.db.session import create_session_factory
from bot.integrations.telegram import TelegramChannelAdapter
from bot.modules.leads.use_cases import NotifyLeadUseCase

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    init_glitchtip(settings)
    if not settings.api_token and not settings.lead_api_token:
        raise SystemExit(
            "API_TOKEN (или LEAD_API_TOKEN) должен быть задан в .env. "
            "Сервис принимает оба заголовка: x-api-token и legacy x-lead-token."
        )
    lead_notify_use_case = None
    if settings.leads_chat_id:
        telegram_adapter = TelegramChannelAdapter(Bot(settings.bot_token))
        lead_notify_use_case = NotifyLeadUseCase(settings, telegram_adapter)
    else:
        logger.warning("LEADS_CHAT_ID не задан: POST /api/leads будет отвечать 503")
    app = create_api_app(settings, create_session_factory(), lead_notify_use_case)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
