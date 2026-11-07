import base64
from typing import Any, cast

import pytest
from aiohttp import ClientSession

from vashfindir.core.config import Settings
from vashfindir.integrations.image_generator import (
    GeneratedImage,
    ImageGenerationError,
)
from vashfindir.integrations.image_generator_factory import create_image_generator
from vashfindir.integrations.minimax_image_generator import MiniMaxImageGenerator


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


def _adapter(session: _FakeSession) -> MiniMaxImageGenerator:
    return MiniMaxImageGenerator(
        cast(ClientSession, session),
        url="https://api.minimax.io/v1/image_generation",
        api_key="secret-key",
        timeout_seconds=120,
    )


def _minimax_payload(image_content: bytes) -> dict[str, Any]:
    return {
        "id": "minimax-trace-1",
        "data": {"image_base64": [base64.b64encode(image_content).decode()]},
        "metadata": {"failed_count": "0", "success_count": "1"},
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }


async def test_minimax_posts_image_generation_request() -> None:
    image_content = b"fake png"
    session = _FakeSession(payload=_minimax_payload(image_content))

    result = await _adapter(session).generate(
        prompt="Visual subject: test",
        negative_prompt="text, watermark",
        model="image-01",
        width=1122,
        height=1402,
    )

    assert result == GeneratedImage(
        content=image_content,
        provider_request_id="minimax-trace-1",
        mime_type="image/png",
    )
    request = session.requests[0]
    assert request["url"] == "https://api.minimax.io/v1/image_generation"
    assert request["headers"] == {"Authorization": "Bearer secret-key"}
    assert request["json"] == {
        "model": "image-01",
        "prompt": "Visual subject: test\nAvoid: text, watermark",
        "aspect_ratio": "3:4",
        "response_format": "base64",
        "n": 1,
    }


@pytest.mark.parametrize(
    ("width", "height", "expected_ratio"),
    [
        (1080, 1080, "1:1"),
        (1920, 1080, "16:9"),
        (1400, 1050, "4:3"),
        (1248, 832, "3:2"),
        (832, 1248, "2:3"),
        (1122, 1402, "3:4"),
        (720, 1280, "9:16"),
        (1344, 576, "21:9"),
    ],
)
def test_minimax_maps_dimensions_to_preset_aspect_ratio(
    width: int,
    height: int,
    expected_ratio: str,
) -> None:
    assert MiniMaxImageGenerator._aspect_ratio(width, height) == expected_ratio


async def test_minimax_decodes_data_url_prefixed_image() -> None:
    image_content = b"fake png"
    payload = _minimax_payload(image_content)
    encoded = payload["data"]["image_base64"][0]
    payload["data"]["image_base64"][0] = f"data:image/png;base64,{encoded}"
    session = _FakeSession(payload=payload)

    result = await _adapter(session).generate(
        prompt="prompt",
        negative_prompt="",
        model="image-01",
        width=1080,
        height=1080,
    )

    assert result.content == image_content


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"base_resp": {"status_code": 0, "status_msg": "success"}},
        {"data": {}},
        {"data": {"image_base64": []}},
        {"data": {"image_base64": ["not-base64!"]}},
        {"data": {"image_base64": [""]}},
    ],
)
async def test_minimax_rejects_invalid_payload(payload: dict[str, Any]) -> None:
    session = _FakeSession(payload=payload)

    with pytest.raises(ImageGenerationError):
        await _adapter(session).generate(
            prompt="prompt",
            negative_prompt="",
            model="image-01",
            width=1080,
            height=1080,
        )


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (1002, "превышен лимит запросов API"),
        (1004, "неверный API-ключ"),
        (1008, "недостаточно средств на балансе API"),
        (1026, "генерация отклонена правилами контента провайдера"),
    ],
)
async def test_minimax_business_error_becomes_generation_error(
    status_code: int,
    reason: str,
) -> None:
    session = _FakeSession(
        payload={
            "data": {},
            "base_resp": {"status_code": status_code, "status_msg": "boom"},
        }
    )

    with pytest.raises(ImageGenerationError, match=reason) as exc_info:
        await _adapter(session).generate(
            prompt="prompt",
            negative_prompt="",
            model="image-01",
            width=1080,
            height=1080,
        )

    assert exc_info.value.error_code == str(status_code)
    assert "boom" in str(exc_info.value)


async def test_minimax_rate_limit_error_is_retried() -> None:
    image_content = b"fake png"
    session = _FakeSession(
        responses=[
            _FakeResponse(
                200,
                {
                    "data": {},
                    "base_resp": {"status_code": 1002, "status_msg": "rate limit"},
                },
            ),
            _FakeResponse(200, _minimax_payload(image_content)),
        ]
    )
    adapter = MiniMaxImageGenerator(
        cast(ClientSession, session),
        url="https://api.minimax.io/v1/image_generation",
        api_key="secret-key",
        timeout_seconds=120,
        max_attempts=2,
        retry_backoff_seconds=0,
    )

    result = await adapter.generate(
        prompt="prompt",
        negative_prompt="",
        model="image-01",
        width=1080,
        height=1080,
    )

    assert result.content == image_content
    assert len(session.requests) == 2


def test_factory_selects_minimax_for_minimax_url() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://api.minimax.io/v1/image_generation",
            "image_provider_api_key": "secret-key",
            "image_provider_model": "image-01",
        }
    )

    generator = create_image_generator(settings, cast(ClientSession, _FakeSession()))

    assert type(generator) is MiniMaxImageGenerator
    assert generator._default_model == "image-01"


def test_factory_selects_minimax_for_china_region_url() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://api.minimaxi.com/v1/image_generation",
            "image_provider_api_key": "secret-key",
            "image_provider_model": "image-01",
        }
    )

    generator = create_image_generator(settings, cast(ClientSession, _FakeSession()))

    assert type(generator) is MiniMaxImageGenerator
