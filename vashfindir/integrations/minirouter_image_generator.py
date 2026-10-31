from typing import Any

from vashfindir.integrations.openai_compatible_image_generator import (
    OpenAICompatibleImageGenerator,
)


class MiniRouterImageGenerator(OpenAICompatibleImageGenerator):
    """MiniRouter image adapter with model-specific controls for GPT Image 2.5."""

    def _build_payload(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        payload = super()._build_payload(
            prompt=prompt,
            negative_prompt=negative_prompt,
            model=model,
            width=width,
            height=height,
        )
        payload.update(
            {
                "size": "1024x1024",
                "quality": "low",
                "background": "auto",
                "moderation": "auto",
            }
        )
        return payload
