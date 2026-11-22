import asyncio
from typing import cast

import sentry_sdk
from aiohttp import ClientError, ClientSession, ClientTimeout
from pydantic import SecretStr
from sentry_sdk.client import NonRecordingClient

_NOT_FOUND = {"NOT_FOUND", "ERROR_NOT_FOUND", "CRM_LEAD_NOT_FOUND"}
_RATE_LIMIT = {"QUERY_LIMIT_EXCEEDED", "OPERATION_TIME_LIMIT"}
_AUTH_ERRORS = {"NO_AUTH_FOUND", "INVALID_CREDENTIALS", "ACCESS_DENIED", "OVERLOAD_LIMIT"}
_TIMEOUT = ClientTimeout(total=15, connect=5)


class BitrixError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        not_found: bool = False,
        retry_after: int = 0,
    ) -> None:
        super().__init__(code)
        self.not_found = not_found
        self.retry_after = retry_after


class BitrixClient:
    def __init__(self, session: ClientSession, *, min_interval: float = 0.5) -> None:
        self._session = session
        self._interval = min_interval
        self._next_request = 0.0
        self._lock = asyncio.Lock()

    async def _request(
        self,
        webhook: SecretStr,
        method: str,
        data: dict[str, object],
    ) -> object:
        async with self._lock:
            loop = asyncio.get_running_loop()
            delay = self._next_request - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request = loop.time() + self._interval

            # The credential is in the URL path, which aiohttp spans normally record.
            with sentry_sdk.new_scope() as scope:
                scope.set_client(NonRecordingClient())
                try:
                    async with self._session.post(
                        webhook.get_secret_value() + method,
                        json=data,
                        timeout=_TIMEOUT,
                        allow_redirects=False,
                    ) as response:
                        status = response.status
                        retry_header = response.headers.get("Retry-After", "")
                        retry_after = (
                            int(retry_header)
                            if retry_header.isdecimal() and (len(retry_header) < 10)
                            else 0
                        )
                        try:
                            raw = await response.json(content_type=None)
                        except ValueError:
                            raw = None
                except (ClientError, TimeoutError, ValueError):
                    raise BitrixError("network_error") from None

        document = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        code_value = document.get("error")
        code = code_value if isinstance(code_value, str) else ""
        description = document.get("error_description")
        if method == "crm.lead.update" and (
            code in _NOT_FOUND
            or (isinstance(description, str) and description.strip().lower() == "not found")
        ):
            raise BitrixError("lead_not_found", not_found=True)
        if status == 429 or code in _RATE_LIMIT:
            raise BitrixError("rate_limited", retry_after=retry_after)
        if status in (401, 403) or code in _AUTH_ERRORS:
            raise BitrixError("authorization_failed")
        if not 200 <= status < 300:
            raise BitrixError(f"http_{status}", retry_after=retry_after)
        if "error" in document:
            raise BitrixError("bitrix_request_failed")
        if "result" not in document:
            raise BitrixError("invalid_response")
        return document["result"]

    async def find_lead(
        self,
        webhook: SecretStr,
        originator_id: str,
        origin_id: str,
    ) -> int | None:
        result = await self._request(
            webhook,
            "crm.lead.list",
            {
                "filter": {"=ORIGINATOR_ID": originator_id, "=ORIGIN_ID": origin_id},
                "select": ["ID"],
            },
        )
        if not isinstance(result, list):
            raise BitrixError("invalid_response")
        if len(result) > 1:
            raise BitrixError("multiple_leads_found")
        if not result:
            return None
        row = result[0]
        if not isinstance(row, dict):
            raise BitrixError("invalid_response")
        return _response_id(row.get("ID"))

    async def add_lead(self, webhook: SecretStr, fields: dict[str, object]) -> int:
        return _response_id(await self._request(webhook, "crm.lead.add", {"fields": fields}))

    async def update_lead(
        self,
        webhook: SecretStr,
        lead_id: int,
        fields: dict[str, object],
    ) -> None:
        result = await self._request(webhook, "crm.lead.update", {"id": lead_id, "fields": fields})
        if result is not True:
            raise BitrixError("invalid_response")

    async def find_comment(
        self,
        webhook: SecretStr,
        lead_id: int,
        marker: str,
    ) -> int | None:
        result = await self._request(
            webhook,
            "crm.timeline.comment.list",
            {
                "filter": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead"},
                "order": {"ID": "DESC"},
                "select": ["ID", "COMMENT"],
            },
        )
        if not isinstance(result, list):
            raise BitrixError("invalid_response")
        for row in result:
            if isinstance(row, dict) and marker in str(row.get("COMMENT", "")):
                return _response_id(row.get("ID"))
        return None

    async def add_comment(self, webhook: SecretStr, lead_id: int, text: str) -> int:
        return _response_id(
            await self._request(
                webhook,
                "crm.timeline.comment.add",
                {
                    "fields": {"ENTITY_ID": lead_id, "ENTITY_TYPE": "lead", "COMMENT": text},
                },
            )
        )


def _response_id(value: object) -> int:
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 19:
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**63:
        raise BitrixError("invalid_response")
    return value
