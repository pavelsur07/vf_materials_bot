import logging

import uvicorn
from aiogram import Bot

from vashfindir.apps.admin.app import create_admin_app
from vashfindir.core.config import get_settings
from vashfindir.core.glitchtip import init_glitchtip
from vashfindir.db.session import create_session_factory
from vashfindir.domain.slides import default_slide_style
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.modules.leads.use_cases import NotifyLeadUseCase
from vashfindir.modules.slides.use_cases import QueueSlideGenerationUseCase


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    init_glitchtip(settings)
    if not settings.admin_secret_key or not settings.admin_password_hash:
        raise SystemExit(
            "ADMIN_SECRET_KEY и ADMIN_PASSWORD_HASH должны быть заданы в .env. "
            "Хэш пароля: uv run python -m vashfindir.apps.admin.hashpw"
        )
    telegram_bot = None
    lead_notify_use_case = None
    if settings.leads_chat_id:
        telegram_bot = Bot(settings.bot_token)
        telegram_adapter = TelegramChannelAdapter(telegram_bot)
        lead_notify_use_case = NotifyLeadUseCase(settings, telegram_adapter)
    slide_generation_use_case = QueueSlideGenerationUseCase(
        default_slide_style(),
        generation_model=settings.image_provider_model
        if settings.image_provider_configured
        else None,
    )
    app = create_admin_app(
        settings,
        create_session_factory(),
        lead_notify_use_case=lead_notify_use_case,
        slide_generation_use_case=slide_generation_use_case,
        telegram_bot=telegram_bot,
    )
    uvicorn.run(app, host=settings.admin_host, port=settings.admin_port)


if __name__ == "__main__":
    main()
