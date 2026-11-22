import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiohttp import ClientSession
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.apps.worker.handlers import (
    DAILY_STATS,
    DAILY_STATS_INTERVAL,
    HANDLERS,
    Handler,
    build_handlers,
    recover_interrupted_work,
)
from vashfindir.core.config import Settings, get_settings
from vashfindir.core.glitchtip import init_glitchtip
from vashfindir.db.session import create_session_factory
from vashfindir.domain.attribution.bitrix_queue import BITRIX_JOB
from vashfindir.domain.attribution.summary import SUMMARY_JOB, enqueue_daily_summary
from vashfindir.domain.jobs import claim_due_job, complete_job, ensure_scheduled, fail_job, utcnow
from vashfindir.integrations.bitrix24 import BitrixClient
from vashfindir.integrations.image_generator_factory import create_image_generator
from vashfindir.integrations.telegram_delivery import TelegramDelivery
from vashfindir.modules.attribution.bitrix_sync import BitrixSync, enqueue_bitrix_work
from vashfindir.modules.attribution.notifications import AttributionNotifications

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5.0


async def run_loop(
    stop: asyncio.Event,
    handlers: dict[str, Handler] | None = None,
    reconcile: Callable[[AsyncSession], Awaitable[None]] | None = None,
) -> None:
    session_factory = create_session_factory()
    handler_map = handlers or HANDLERS

    async with session_factory() as session:
        await recover_interrupted_work(session)
        async with session.begin():
            await ensure_scheduled(session, DAILY_STATS, DAILY_STATS_INTERVAL)

    loop = asyncio.get_running_loop()
    next_reconcile = 0.0
    while not stop.is_set():
        if reconcile is not None and loop.time() >= next_reconcile:
            next_reconcile = loop.time() + POLL_INTERVAL_SECONDS
            try:
                async with session_factory() as session:
                    await reconcile(session)
            except Exception:
                logger.exception("Could not reconcile attribution jobs")
        async with session_factory() as session:
            job = await claim_due_job(session)
        if job is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        handler = handler_map.get(job.type)
        if handler is None:
            logger.error("Job %s: unknown type %r", job.id, job.type)
            async with session_factory() as session:
                await fail_job(session, job, f"unknown job type: {job.type}")
            continue

        try:
            async with session_factory() as session:
                await handler(job, session)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job.id, job.type)
            async with session_factory() as session:
                await fail_job(session, job, str(exc))
        else:
            async with session_factory() as session:
                await complete_job(session, job)


async def _run(settings: Settings) -> None:
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    async with contextlib.AsyncExitStack() as stack:
        http_session = await stack.enter_async_context(ClientSession())
        image_generator = create_image_generator(settings, http_session)
        handlers = build_handlers(image_generator)
        reconcile = None
        if settings.attribution_enabled:
            notifications = None
            if settings.bot_token:
                bot = await stack.enter_async_context(Bot(settings.bot_token).context())
                delivery = TelegramDelivery(bot, settings.attribution_magnet_dir)
                notifications = AttributionNotifications(
                    settings.attribution_bootstrap_admin_tg_ids, delivery
                )
                handlers[SUMMARY_JOB] = notifications.summary_job
            bitrix_sync = BitrixSync(
                BitrixClient(http_session),
                settings.attribution_secret_key,
                notifications,
            )
            handlers[BITRIX_JOB] = bitrix_sync.handle_job

            async def reconcile_attribution(session: AsyncSession) -> None:
                await enqueue_bitrix_work(session, settings.attribution_secret_key)
                if notifications is not None:
                    async with session.begin():
                        await enqueue_daily_summary(
                            session,
                            settings.attribution_bootstrap_admin_tg_ids,
                            utcnow(),
                        )

            reconcile = reconcile_attribution
        await run_loop(stop, handlers, reconcile)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    init_glitchtip(settings)
    if not settings.worker_enabled:
        logger.info("WORKER_ENABLED не включён в .env — воркер не запущен")
        return
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(settings))


if __name__ == "__main__":
    main()
