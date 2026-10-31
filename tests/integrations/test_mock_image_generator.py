from pathlib import Path

import pytest

from vashfindir.integrations.image_generator import ImageGenerationError
from vashfindir.integrations.mock_image_generator import (
    DEFAULT_MOCK_IMAGE,
    MockImageGenerator,
)


async def test_mock_returns_content_from_prepared_file(tmp_path: Path) -> None:
    image_path = tmp_path / "prepared.png"
    image_path.write_bytes(b"prepared image")
    generator = MockImageGenerator(image_path, provider_request_id="mock-request-7")

    result = await generator.generate(
        prompt="prompt",
        negative_prompt="negative",
        model="mock-model",
        width=1080,
        height=1350,
    )

    assert result.content == b"prepared image"
    assert result.provider_request_id == "mock-request-7"
    assert result.mime_type == "image/png"


async def test_mock_returns_deterministic_default_image() -> None:
    generator = MockImageGenerator()

    first = await generator.generate(
        prompt="prompt",
        negative_prompt="negative",
        model="mock-model",
        width=1080,
        height=1350,
    )
    second = await generator.generate(
        prompt="another prompt",
        negative_prompt="negative",
        model="mock-model",
        width=1080,
        height=1350,
    )

    assert first.content == DEFAULT_MOCK_IMAGE
    assert first.content == second.content
    assert first.provider_request_id == second.provider_request_id


async def test_mock_rejects_empty_prepared_file(tmp_path: Path) -> None:
    image_path = tmp_path / "empty.png"
    image_path.write_bytes(b"")
    generator = MockImageGenerator(image_path)

    with pytest.raises(ImageGenerationError, match="empty"):
        await generator.generate(
            prompt="prompt",
            negative_prompt="negative",
            model="mock-model",
            width=1080,
            height=1350,
        )
