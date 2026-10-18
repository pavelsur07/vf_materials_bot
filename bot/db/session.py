from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.core.config import get_settings


def _apply_pragmas(engine: AsyncEngine) -> None:
    # Сервисы (bot, admin, api, worker) пишут в одну SQLite из разных процессов:
    # WAL + busy_timeout снимают «database is locked» при конкурентных коммитах.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_engine() -> AsyncEngine:
    engine = create_async_engine(get_settings().database_url)
    _apply_pragmas(engine)
    return engine


def create_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or create_engine(), expire_on_commit=False)
