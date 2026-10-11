from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.core.config import get_settings


def create_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


def create_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or create_engine(), expire_on_commit=False)
