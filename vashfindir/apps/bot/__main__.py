import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from vashfindir.apps.bot.handlers import get_routers
from vashfindir.apps.bot.middlewares.db import DbSessionMiddleware
from vashfindir.apps.bot.middlewares.di import DiMiddleware
from vashfindir.core.config import Settings, get_settings
from vashfindir.core.glitchtip import init_glitchtip
from vashfindir.db.session import create_session_factory
from vashfindir.integrations.telegram import TelegramChannelAdapter
from vashfindir.modules.onboarding.use_cases import OnboardingUseCase

logger = logging.getLogger(__name__)


def build_dispatcher(bot: Bot, settings: Settings) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    telegram_adapter = TelegramChannelAdapter(bot)
    onboarding_use_case = OnboardingUseCase(settings, telegram_adapter)
    dp.update.middleware(DbSessionMiddleware(create_session_factory()))
    dp.update.middleware(DiMiddleware(onboarding_use_case))
    for router in get_routers():
        dp.include_router(router)
    return dp


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    async def on_startup() -> None:
        await bot.set_webhook(settings.webhook_url, secret_token=settings.webhook_secret)
        logger.info("Webhook set: %s", settings.webhook_url)

    async def on_shutdown() -> None:
        await bot.delete_webhook()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(
        app, path=settings.webhook_path
    )
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=settings.webapp_host, port=settings.webapp_port)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    init_glitchtip(settings)
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен.")
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(bot, settings)
    if settings.mode == "webhook":
        run_webhook(bot, dp, settings)
    else:
        asyncio.run(run_polling(bot, dp))


if __name__ == "__main__":
    main()
