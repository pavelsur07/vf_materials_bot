from collections.abc import AsyncIterator
from typing import cast

from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_templates(request: Request) -> Jinja2Templates:
    return cast(Jinja2Templates, request.app.state.templates)
