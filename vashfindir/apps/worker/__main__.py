import asyncio
import contextlib
import logging
import signal

from aiohttp import ClientSession

from vashfindir.apps.worker.handlers import (
    DAILY_STATS,
    DAILY_STATS_INTERVAL,
    HANDLERS,
    Handler,
    build_handlers,
)
from vashfindir.core.config import Settings, get_settings
from vashfindir.core.glitchtip import init_glitchtip
from vashfindir.db.session import create_session_factory
from vashfindir.domain.jobs import claim_due_job, complete_job, ensure_scheduled, fail_job
from vashfindir.integrations.image_generator_factory import create_image_generator

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5.0


async def run_loop(
    stop: asyncio.Event,
    handlers: dict[str, Handler] | None = None,
) -> None:
    session_factory = create_session_factory()
    handler_map = handlers or HANDLERS

    async with session_factory() as session:
        await ensure_scheduled(session, DAILY_STATS, DAILY_STATS_INTERVAL)

    while not stop.is_set():
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
    async with ClientSession() as http_session:
        image_generator = create_image_generator(settings, http_session)
        await run_loop(stop, build_handlers(image_generator))


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
