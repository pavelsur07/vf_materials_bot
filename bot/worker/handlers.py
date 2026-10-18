import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Job
from bot.services.jobs import enqueue_job, utcnow
from bot.services.stats import count_users

logger = logging.getLogger(__name__)

DAILY_STATS = "daily_stats"
DAILY_STATS_INTERVAL = timedelta(days=1)

Handler = Callable[[Job, AsyncSession], Awaitable[None]]


async def _daily_stats(job: Job, session: AsyncSession) -> None:
    total = await count_users(session)
    logger.info("daily_stats: users=%s", total)
    # Сама задача ставит следующий запуск: текущая в статусе running,
    # поэтому ensure_scheduled здесь не подошёл бы.
    await enqueue_job(session, DAILY_STATS, run_at=utcnow() + DAILY_STATS_INTERVAL)


HANDLERS: dict[str, Handler] = {DAILY_STATS: _daily_stats}
