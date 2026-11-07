import base64
import binascii
import re
from typing import Any

from vashfindir.integrations.image_generator import (
    GeneratedImage,
    HttpImageGenerator,
    ImageGenerationError,
    ImageProviderUnavailableError,
)

# MiniMax сообщает о бизнес-ошибках (лимиты, баланс, контент) внутри HTTP 200
# через base_resp.status_code, а не через HTTP-статус.
# См. https://platform.minimax.io/docs/api-reference/image-generation-t2i
_BUSINESS_ERROR_REASONS = {
    1002: "превышен лимит запросов API",
    1004: "неверный API-ключ",
    1008: "недостаточно средств на балансе API",
    1026: "генерация отклонена правилами контента провайдера",
}
_RETRYABLE_BUSINESS_CODES = {1002}

# Пресеты aspect_ratio модели image-01: запрашиваемые width/height слайдов
# редко совпадают с ограничениями MiniMax (512–2048, кратно 8), поэтому
# округляем до ближайшего пресета, как OpenAI-адаптер округляет size.
_ASPECT_RATIOS: tuple[tuple[str, float], ...] = (
    ("1:1", 1.0),
    ("16:9", 16 / 9),
    ("4:3", 4 / 3),
    ("3:2", 3 / 2),
    ("2:3", 2 / 3),
    ("3:4", 3 / 4),
    ("9:16", 9 / 16),
    ("21:9", 21 / 9),
)

_DATA_URL_PREFIX = re.compile(r"^data:image/[a-z0-9.+-]+;base64,", re.IGNORECASE)


class MiniMaxImageGenerator(HttpImageGenerator):
    """MiniMax image-01 adapter (POST {base}/v1/image_generation)."""

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
            "aspect_ratio": self._aspect_ratio(width, height),
            "response_format": "base64",
            "n": 1,
        }

    def _parse_response(self, payload: Any, fallback_request_id: str | None) -> GeneratedImage:
        if not isinstance(payload, dict):
            raise ImageGenerationError("image provider returned an invalid payload")
        self._raise_for_business_error(payload)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ImageGenerationError("image provider returned no image data")
        encoded_images = data.get("image_base64")
        if not isinstance(encoded_images, list) or not encoded_images:
            raise ImageGenerationError("image provider returned no image content")
        encoded = encoded_images[0]
        if not isinstance(encoded, str) or not encoded:
            raise ImageGenerationError("image provider returned no image content")
        encoded = _DATA_URL_PREFIX.sub("", encoded)
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageGenerationError("image provider returned invalid image content") from exc
        if not content:
            raise ImageGenerationError("image provider returned empty image content")

        raw_request_id = payload.get("id") or fallback_request_id
        if not isinstance(raw_request_id, str) or not raw_request_id:
            raise ImageGenerationError("image provider returned no request id")

        return GeneratedImage(content=content, provider_request_id=raw_request_id)

    def _raise_for_business_error(self, payload: dict[str, Any]) -> None:
        base_resp = payload.get("base_resp")
        if not isinstance(base_resp, dict):
            return
        raw_code = base_resp.get("status_code")
        if isinstance(raw_code, bool):
            return
        if isinstance(raw_code, int):
            code = raw_code
        elif isinstance(raw_code, str) and raw_code.isdigit():
            code = int(raw_code)
        else:
            return
        if code == 0:
            return
        reason = _BUSINESS_ERROR_REASONS.get(code, "ошибка API генерации")
        message = f"image provider returned status_code {code}: {reason}"
        status_msg = self._safe_error_field(base_resp.get("status_msg"))
        if status_msg:
            message += f"; status_msg={status_msg}"
        error_class = (
            ImageProviderUnavailableError
            if code in _RETRYABLE_BUSINESS_CODES
            else ImageGenerationError
        )
        raise error_class(message, error_code=str(code))

    @staticmethod
    def _aspect_ratio(width: int, height: int) -> str:
        target = width / height
        name, _ = min(_ASPECT_RATIOS, key=lambda item: abs(item[1] / target - 1))
        return name
