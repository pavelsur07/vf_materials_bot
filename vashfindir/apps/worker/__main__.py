import asyncio
import contextlib
import logging
import signal

from vashfindir.apps.worker.handlers import DAILY_STATS, DAILY_STATS_INTERVAL, HANDLERS
from vashfindir.core.config import get_settings
from vashfindir.core.glitchtip import init_glitchtip
from vashfindir.db.session import create_session_factory
from vashfindir.domain.jobs import claim_due_job, complete_job, ensure_scheduled, fail_job

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5.0


async def run_loop(stop: asyncio.Event) -> None:
    session_factory = create_session_factory()

    async with session_factory() as session:
        await ensure_scheduled(session, DAILY_STATS, DAILY_STATS_INTERVAL)

    while not stop.is_set():
        async with session_factory() as session:
            job = await claim_due_job(session)
        if job is None:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue

        handler = HANDLERS.get(job.type)
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


async def _run() -> None:
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    await run_loop(stop)


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
        asyncio.run(_run())


if __name__ == "__main__":
    main()
