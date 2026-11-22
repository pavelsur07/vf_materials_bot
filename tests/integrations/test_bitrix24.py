from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectionError
from pydantic import SecretStr

from vashfindir.integrations.bitrix24 import BitrixClient, BitrixError

HOOK = SecretStr("https://example.bitrix24.ru/rest/5/private-test-key/")


def response(session: MagicMock, status: int, payload: dict, headers: dict | None = None) -> None:
    result = MagicMock(status=status, headers=headers or {})
    result.json = AsyncMock(return_value=payload)
    session.post.return_value.__aenter__.return_value = result


async def test_add_posts_fields_without_forwarding_secret_on_redirect() -> None:
    session = MagicMock()
    response(session, 200, {"result": "987"})
    adapter = BitrixClient(session, min_interval=0)
    assert await adapter.add_lead(HOOK, {"TITLE": "Telegram"}) == 987
    args, kwargs = session.post.call_args
    assert args == (HOOK.get_secret_value() + "crm.lead.add",)
    assert kwargs["json"] == {"fields": {"TITLE": "Telegram"}}
    assert kwargs["allow_redirects"] is False


async def test_remote_descriptions_and_transport_errors_do_not_leak() -> None:
    session = MagicMock()
    adapter = BitrixClient(session, min_interval=0)
    response(
        session,
        503,
        {
            "error": "QUERY_LIMIT_EXCEEDED",
            "error_description": HOOK.get_secret_value(),
        },
        {"Retry-After": "90"},
    )
    with pytest.raises(BitrixError, match="^rate_limited$") as error:
        await adapter.add_lead(HOOK, {})
    assert error.value.retry_after == 90

    session.post.side_effect = ClientConnectionError(HOOK.get_secret_value())
    with pytest.raises(BitrixError, match="^network_error$") as error:
        await adapter.add_lead(HOOK, {})
    assert error.value.__suppress_context__
