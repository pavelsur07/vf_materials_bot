import asyncio
import base64
from pathlib import Path

from vashfindir.integrations.image_generator import GeneratedImage, ImageGenerationError

DEFAULT_MOCK_IMAGE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class MockImageGenerator:
    """Deterministic generator used before a real provider is configured."""

    def __init__(
        self,
        image_path: Path | None = None,
        *,
        provider_request_id: str = "mock-request-1",
    ) -> None:
        if not provider_request_id:
            raise ValueError("provider_request_id must not be empty")
        self._image_path = image_path
        self._provider_request_id = provider_request_id

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        if self._image_path is None:
            content = DEFAULT_MOCK_IMAGE
        else:
            content = await asyncio.to_thread(self._image_path.read_bytes)
        if not content:
            raise ImageGenerationError("mock image is empty")
        return GeneratedImage(content=content, provider_request_id=self._provider_request_id)
