import asyncio
import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError

from vashfindir.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)


class ImageGenerationError(IntegrationError):
    """Raised when an image provider cannot return a generated image."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_type = error_type
        self.request_id = request_id


class ImageProviderUnavailableError(ImageGenerationError):
    """Raised for temporary provider failures that may be retried."""


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    content: bytes
    provider_request_id: str
    mime_type: str = "image/png"


class ImageGenerator(Protocol):
    """Provider-independent image generation contract."""

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> GeneratedImage: ...


class HttpImageGenerator:
    """JSON-over-HTTP adapter for an image generation provider."""

    def __init__(
        self,
        session: ClientSession,
        *,
        url: str,
        api_key: str,
        timeout_seconds: float,
        default_model: str | None = None,
        max_attempts: int = 1,
        retry_backoff_seconds: float = 0,
    ) -> None:
        if not url.strip() or not api_key.strip():
            raise ValueError("image provider url and api key are required")
        if timeout_seconds <= 0:
            raise ValueError("image provider timeout must be positive")
        if max_attempts < 1:
            raise ValueError("image provider max_attempts must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("image provider retry backoff must not be negative")
        self._session = session
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._default_model = default_model or None
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = retry_backoff_seconds

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        selected_model = self._default_model or model
        payload = self._build_payload(
            prompt=prompt,
            negative_prompt=negative_prompt,
            model=selected_model,
            width=width,
            height=height,
        )

        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._generate_once(payload)
            except ImageProviderUnavailableError as exc:
                if attempt == self._max_attempts:
                    raise
                logger.warning(
                    "Image provider attempt %s/%s failed: %s; retrying",
                    attempt,
                    self._max_attempts,
                    exc,
                )
                await asyncio.sleep(self._retry_backoff_seconds * attempt)
        raise AssertionError("unreachable retry loop state")

    def _build_payload(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "response_format": "b64_json",
        }

    async def _generate_once(self, payload: dict[str, Any]) -> GeneratedImage:
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with self._session.post(
                self._url,
                json=payload,
                headers=headers,
                timeout=ClientTimeout(total=self._timeout_seconds),
            ) as response:
                header_request_id = response.headers.get("x-request-id") or response.headers.get(
                    "x-minirouter-request-id"
                )
                if response.status < 200 or response.status >= 300:
                    try:
                        error_payload = await response.json()
                    except (ClientError, TimeoutError, ValueError):
                        # Keep the HTTP classification even if the error body is unreadable.
                        error_payload = None
                    error = self._build_provider_error(
                        response.status, error_payload, header_request_id
                    )
                    logger.error("Image provider request failed: %s", error)
                    raise error
                response_payload = await response.json()
        except (ClientError, TimeoutError, json.JSONDecodeError) as exc:
            raise ImageProviderUnavailableError("image provider request failed") from exc

        return self._parse_response(response_payload, header_request_id)

    def _safe_error_field(self, value: object) -> str | None:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
            return None
        if self._api_key in value or value.lower().startswith("sk-"):
            return None
        return value

    def _build_provider_error(
        self, status: int, payload: object, request_id: str | None
    ) -> ImageGenerationError:
        details = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(details, dict):
            details = {}
        code = self._safe_error_field(details.get("code"))
        error_type = self._safe_error_field(details.get("type"))
        safe_request_id = self._safe_error_field(request_id)
        # Provider messages can echo credentials or user input. Use our own descriptions.
        descriptions = {
            "expired_secret_key": "истёк срок действия API-ключа",
            "invalid_api_key": "неверный API-ключ",
            "insufficient_quota": "исчерпана квота API или требуется пополнение баланса",
            "rate_limit_exceeded": "превышен лимит запросов API",
            "model_not_found": "модель не найдена или недоступна для API-ключа",
            "content_policy_violation": "генерация отклонена правилами контента провайдера",
        }
        fallback = {
            401: "провайдер отклонил авторизацию API-ключа",
            403: "доступ к API запрещён",
            408: "превышено время ожидания ответа API",
            429: "провайдер ограничил запрос: проверьте лимиты и квоту API",
        }
        reason = descriptions.get(code or "") or fallback.get(status, "ошибка API генерации")
        message = f"image provider returned status {status}: {reason}"
        for name, value in (("code", code), ("type", error_type), ("request_id", safe_request_id)):
            if value:
                message += f"; {name}={value}"
        error_class = (
            ImageProviderUnavailableError
            if status in {408, 429} or status >= 500
            else ImageGenerationError
        )
        return error_class(
            message,
            status_code=status,
            error_code=code,
            error_type=error_type,
            request_id=safe_request_id,
        )

    def _parse_response(self, payload: Any, fallback_request_id: str | None) -> GeneratedImage:
        if not isinstance(payload, dict):
            raise ImageGenerationError("image provider returned an invalid payload")
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ImageGenerationError("image provider returned no image data")
        item = data[0]
        if not isinstance(item, dict):
            raise ImageGenerationError("image provider returned invalid image data")

        encoded = item.get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise ImageGenerationError("image provider returned no image content")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenerationError("image provider returned invalid image content") from exc
        if not content:
            raise ImageGenerationError("image provider returned empty image content")

        raw_request_id = item.get("id") or item.get("request_id") or fallback_request_id
        if not isinstance(raw_request_id, str) or not raw_request_id:
            raise ImageGenerationError("image provider returned no request id")
        mime_type = item.get("mime_type", "image/png")
        if not isinstance(mime_type, str) or not mime_type:
            raise ImageGenerationError("image provider returned invalid mime type")

        return GeneratedImage(
            content=content,
            provider_request_id=raw_request_id,
            mime_type=mime_type,
        )
