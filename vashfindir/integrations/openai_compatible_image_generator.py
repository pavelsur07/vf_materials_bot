from typing import Any

from vashfindir.integrations.image_generator import HttpImageGenerator


class OpenAICompatibleImageGenerator(HttpImageGenerator):
    """Images API adapter for OpenAI and OpenAI-compatible gateways."""

    def _build_payload(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        model: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        full_prompt = prompt
        if negative_prompt.strip():
            full_prompt = f"{prompt}\nAvoid: {negative_prompt}"
        return {
            "model": model,
            "prompt": full_prompt,
            "n": 1,
            "size": self._openai_size(width, height),
            "quality": "high",
            "output_format": "png",
            "response_format": "b64_json",
        }

    @staticmethod
    def _openai_size(width: int, height: int) -> str:
        aspect_ratio = width / height
        if aspect_ratio > 1.2:
            return "1536x1024"
        if aspect_ratio < 0.85:
            return "1024x1536"
        return "1024x1024"
