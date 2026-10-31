import base64
from typing import Any, cast

import pytest
from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from vashfindir.core.config import Settings
from vashfindir.integrations.image_generator import (
    GeneratedImage,
    HttpImageGenerator,
    ImageGenerationError,
    ImageProviderUnavailableError,
)
from vashfindir.integrations.image_generator_factory import create_image_generator
from vashfindir.integrations.minirouter_image_generator import MiniRouterImageGenerator
from vashfindir.integrations.mock_image_generator import MockImageGenerator
from vashfindir.integrations.openai_compatible_image_generator import (
    OpenAICompatibleImageGenerator,
)


class _FakeResponse:
    def __init__(
        self,
        status: int,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._payload = payload

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(
        self,
        status: int = 200,
        payload: Any | None = None,
        responses: list[_FakeResponse] | None = None,
    ) -> None:
        self.status = status
        self.payload = payload
        self.responses = list(responses) if responses is not None else None
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append({"url": url, **kwargs})
        if self.responses is not None:
            return self.responses.pop(0)
        return _FakeResponse(self.status, self.payload)


def _adapter(session: _FakeSession) -> HttpImageGenerator:
    return HttpImageGenerator(
        cast(ClientSession, session),
        url="https://image-provider.example/generate",
        api_key="secret-key",
        timeout_seconds=12.5,
    )


async def test_http_generator_posts_request_and_decodes_image() -> None:
    image_content = b"fake png"
    session = _FakeSession(
        payload={
            "data": [
                {
                    "id": "provider-request-1",
                    "b64_json": base64.b64encode(image_content).decode(),
                    "mime_type": "image/png",
                }
            ]
        }
    )

    result = await _adapter(session).generate(
        prompt="Visual subject: test",
        negative_prompt="text",
        model="mock-model",
        width=1080,
        height=1350,
    )

    assert result == GeneratedImage(
        content=image_content,
        provider_request_id="provider-request-1",
        mime_type="image/png",
    )
    request = session.requests[0]
    assert request["url"] == "https://image-provider.example/generate"
    assert request["json"] == {
        "model": "mock-model",
        "prompt": "Visual subject: test",
        "negative_prompt": "text",
        "width": 1080,
        "height": 1350,
        "response_format": "b64_json",
    }
    assert request["headers"] == {"Authorization": "Bearer secret-key"}
    assert request["timeout"].total == 12.5


async def test_http_generator_rejects_provider_error_status() -> None:
    session = _FakeSession(status=500, payload={"error": "boom"})

    with pytest.raises(ImageGenerationError, match="status 500"):
        await _adapter(session).generate(
            prompt="prompt",
            negative_prompt="negative",
            model="model",
            width=1080,
            height=1350,
        )


async def test_http_generator_wraps_network_error() -> None:
    session = _FakeSession(payload=ClientError("connection failed"))

    with pytest.raises(ImageGenerationError, match="request failed"):
        await _adapter(session).generate(
            prompt="prompt",
            negative_prompt="negative",
            model="model",
            width=1080,
            height=1350,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": []},
        {"data": [{"id": "request-1"}]},
        {"data": [{"id": "request-1", "b64_json": "not-base64!"}]},
        {"data": [{"b64_json": base64.b64encode(b"image").decode()}]},
    ],
)
async def test_http_generator_rejects_invalid_payload(payload: dict[str, Any]) -> None:
    session = _FakeSession(payload=payload)

    with pytest.raises(ImageGenerationError):
        await _adapter(session).generate(
            prompt="prompt",
            negative_prompt="negative",
            model="model",
            width=1080,
            height=1350,
        )


async def test_http_generator_uses_request_id_from_response_header() -> None:
    session = _FakeSession(
        responses=[
            _FakeResponse(
                200,
                {"data": [{"b64_json": base64.b64encode(b"image").decode()}]},
                headers={"x-request-id": "header-request-1"},
            )
        ],
    )

    result = await _adapter(session).generate(
        prompt="prompt",
        negative_prompt="negative",
        model="model",
        width=1080,
        height=1350,
    )

    assert result.provider_request_id == "header-request-1"


async def test_http_generator_uses_minirouter_request_id_header() -> None:
    session = _FakeSession(
        responses=[
            _FakeResponse(
                200,
                {"data": [{"b64_json": base64.b64encode(b"image").decode()}]},
                headers={"x-minirouter-request-id": "minirouter-request-1"},
            )
        ],
    )

    result = await _adapter(session).generate(
        prompt="prompt",
        negative_prompt="negative",
        model="model",
        width=1080,
        height=1350,
    )

    assert result.provider_request_id == "minirouter-request-1"


@pytest.mark.parametrize("temporary_status", [408, 429, 500])
async def test_http_generator_retries_temporary_error_and_succeeds(
    temporary_status: int,
) -> None:
    success_payload = {
        "data": [
            {
                "id": "provider-request-2",
                "b64_json": base64.b64encode(b"image").decode(),
            }
        ]
    }
    session = _FakeSession(
        responses=[
            _FakeResponse(temporary_status, {"error": "temporary"}),
            _FakeResponse(200, success_payload),
        ]
    )
    adapter = HttpImageGenerator(
        cast(ClientSession, session),
        url="https://image-provider.example/generate",
        api_key="secret-key",
        timeout_seconds=10,
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    result = await adapter.generate(
        prompt="prompt",
        negative_prompt="negative",
        model="model",
        width=1080,
        height=1350,
    )

    assert result.provider_request_id == "provider-request-2"
    assert len(session.requests) == 2


async def test_http_generator_retries_network_error() -> None:
    success_payload = {
        "data": [
            {
                "id": "provider-request-3",
                "b64_json": base64.b64encode(b"image").decode(),
            }
        ]
    }
    session = _FakeSession(
        responses=[
            _FakeResponse(200, ClientError("connection failed")),
            _FakeResponse(200, success_payload),
        ]
    )
    adapter = HttpImageGenerator(
        cast(ClientSession, session),
        url="https://image-provider.example/generate",
        api_key="secret-key",
        timeout_seconds=10,
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    result = await adapter.generate(
        prompt="prompt",
        negative_prompt="negative",
        model="model",
        width=1080,
        height=1350,
    )

    assert result.provider_request_id == "provider-request-3"
    assert len(session.requests) == 2


async def test_http_generator_does_not_retry_permanent_error() -> None:
    session = _FakeSession(status=401, payload={"error": "invalid api key"})
    adapter = HttpImageGenerator(
        cast(ClientSession, session),
        url="https://image-provider.example/generate",
        api_key="secret-key",
        timeout_seconds=10,
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ImageGenerationError) as exc_info:
        await adapter.generate(
            prompt="prompt",
            negative_prompt="negative",
            model="model",
            width=1080,
            height=1350,
        )

    assert not isinstance(exc_info.value, ImageProviderUnavailableError)
    assert len(session.requests) == 1


async def test_http_generator_does_not_retry_invalid_payload() -> None:
    session = _FakeSession(payload={"data": []})
    adapter = HttpImageGenerator(
        cast(ClientSession, session),
        url="https://image-provider.example/generate",
        api_key="secret-key",
        timeout_seconds=10,
        max_attempts=3,
        retry_backoff_seconds=0,
    )

    with pytest.raises(ImageGenerationError, match="no image data"):
        await adapter.generate(
            prompt="prompt",
            negative_prompt="negative",
            model="model",
            width=1080,
            height=1350,
        )

    assert len(session.requests) == 1


@pytest.mark.parametrize(
    ("width", "height", "expected_size"),
    [
        (1080, 1350, "1024x1536"),
        (1350, 1080, "1536x1024"),
        (1080, 1080, "1024x1024"),
    ],
)
async def test_openai_adapter_builds_compatible_request(
    width: int,
    height: int,
    expected_size: str,
) -> None:
    image_content = b"image"
    session = _FakeSession(
        payload={
            "data": [
                {
                    "id": "provider-request-4",
                    "b64_json": base64.b64encode(image_content).decode(),
                }
            ]
        }
    )
    adapter = OpenAICompatibleImageGenerator(
        cast(ClientSession, session),
        url="https://api.openai.example/v1/images/generations",
        api_key="secret-key",
        timeout_seconds=120,
        default_model="gpt-image-2.5-flare",
    )

    result = await adapter.generate(
        prompt="Visual subject: test",
        negative_prompt="text, watermark",
        model="style-model",
        width=width,
        height=height,
    )

    assert result.content == image_content
    request = session.requests[0]
    assert request["json"] == {
        "model": "gpt-image-2.5-flare",
        "prompt": "Visual subject: test\nAvoid: text, watermark",
        "n": 1,
        "size": expected_size,
        "quality": "high",
        "output_format": "png",
        "response_format": "b64_json",
    }


async def test_minirouter_adapter_uses_model_specific_controls() -> None:
    image_content = b"image"
    session = _FakeSession(
        responses=[
            _FakeResponse(
                200,
                {"data": [{"b64_json": base64.b64encode(image_content).decode()}]},
                headers={"x-minirouter-request-id": "minirouter-request-2"},
            )
        ]
    )
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://api.minirouter.sh/v1/images/generations",
            "image_provider_api_key": "secret-key",
            "image_provider_model": "openai/gpt-image-2.5-flare",
        }
    )
    generator = create_image_generator(settings, cast(ClientSession, session))
    assert type(generator) is MiniRouterImageGenerator

    result = await generator.generate(
        prompt="Visual subject: test",
        negative_prompt="text, watermark",
        model="style-model",
        width=1080,
        height=1350,
    )

    assert result.provider_request_id == "minirouter-request-2"
    request = session.requests[0]
    assert request["json"] == {
        "model": "openai/gpt-image-2.5-flare",
        "prompt": "Visual subject: test\nAvoid: text, watermark",
        "n": 1,
        "size": "1024x1024",
        "quality": "low",
        "output_format": "png",
        "response_format": "b64_json",
        "background": "auto",
        "moderation": "auto",
    }


def test_factory_uses_mock_when_provider_is_not_configured() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "",
            "image_provider_api_key": "",
        }
    )
    generator = create_image_generator(settings, cast(ClientSession, _FakeSession()))

    assert isinstance(generator, MockImageGenerator)


def test_factory_uses_http_provider_when_fully_configured() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://image-provider.example/generate",
            "image_provider_api_key": "secret-key",
            "image_provider_model": "custom-image-model",
            "image_provider_timeout_seconds": 30,
            "image_provider_retry_attempts": 3,
            "image_provider_retry_backoff_seconds": 0.5,
        }
    )

    generator = create_image_generator(settings, cast(ClientSession, _FakeSession()))

    assert type(generator) is OpenAICompatibleImageGenerator
    assert generator._default_model == "custom-image-model"
    assert generator._max_attempts == 3
    assert generator._retry_backoff_seconds == 0.5


def test_factory_rejects_partial_provider_configuration() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://image-provider.example/generate",
            "image_provider_api_key": "",
        }
    )

    with pytest.raises(ValueError, match="configured together"):
        create_image_generator(settings, cast(ClientSession, _FakeSession()))
