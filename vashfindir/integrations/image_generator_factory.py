from aiohttp import ClientSession

from vashfindir.core.config import Settings
from vashfindir.integrations.image_generator import ImageGenerator
from vashfindir.integrations.minirouter_image_generator import MiniRouterImageGenerator
from vashfindir.integrations.mock_image_generator import MockImageGenerator
from vashfindir.integrations.openai_compatible_image_generator import (
    OpenAICompatibleImageGenerator,
)


def create_image_generator(settings: Settings, session: ClientSession) -> ImageGenerator:
    """Build a configured provider or fall back to the deterministic mock."""
    has_url = bool(settings.image_provider_url.strip())
    has_api_key = bool(settings.image_provider_api_key.strip())
    if has_url != has_api_key:
        raise ValueError("image provider url and api key must be configured together")
    if has_url and has_api_key:
        is_minirouter = "minirouter.sh" in settings.image_provider_url or (
            settings.image_provider_model.startswith("openai/gpt-image-2.5-")
        )
        generator_class = (
            MiniRouterImageGenerator if is_minirouter else OpenAICompatibleImageGenerator
        )
        return generator_class(
            session,
            url=settings.image_provider_url,
            api_key=settings.image_provider_api_key,
            timeout_seconds=settings.image_provider_timeout_seconds,
            default_model=settings.image_provider_model,
            max_attempts=settings.image_provider_retry_attempts,
            retry_backoff_seconds=settings.image_provider_retry_backoff_seconds,
        )
    return MockImageGenerator()
