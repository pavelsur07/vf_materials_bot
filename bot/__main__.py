import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import get_settings
from bot.db.session import create_session_factory
from bot.handlers import get_routers
from bot.middlewares.db import DbSessionMiddleware

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbSessionMiddleware(create_session_factory()))
    for router in get_routers():
        dp.include_router(router)
    return dp


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    settings = get_settings()

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
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен.")
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    if settings.mode == "webhook":
        run_webhook(bot, dp)
    else:
        asyncio.run(run_polling(bot, dp))


if __name__ == "__main__":
    main()
