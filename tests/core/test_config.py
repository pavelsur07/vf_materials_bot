import pytest
from pydantic import ValidationError

from vashfindir.core.config import Settings


def test_blank_leads_topic_id_defaults_to_zero() -> None:
    settings = Settings.model_validate({"leads_topic_id": ""})

    assert settings.leads_topic_id == 0


def test_blank_leads_chat_id_defaults_to_zero() -> None:
    settings = Settings.model_validate({"leads_chat_id": ""})

    assert settings.leads_chat_id == 0


def test_image_provider_defaults_to_mock_mode() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "",
            "image_provider_api_key": "",
            "image_provider_model": "gpt-image-2.5-flare",
            "image_provider_timeout_seconds": 120,
            "image_provider_retry_attempts": 2,
            "image_provider_retry_backoff_seconds": 1,
        }
    )

    assert settings.image_provider_url == ""
    assert settings.image_provider_api_key == ""
    assert settings.image_provider_model == "gpt-image-2.5-flare"
    assert settings.image_provider_timeout_seconds == 120.0
    assert settings.image_provider_retry_attempts == 2
    assert settings.image_provider_retry_backoff_seconds == 1.0
    assert settings.image_provider_configured is False


def test_image_provider_configured_requires_url_and_api_key() -> None:
    settings = Settings.model_validate(
        {
            "image_provider_url": "https://api.openai.example/v1/images/generations",
            "image_provider_api_key": "secret-key",
        }
    )

    assert settings.image_provider_configured is True


@pytest.mark.parametrize(
    "value",
    [
        {"image_provider_timeout_seconds": 0},
        {"image_provider_retry_attempts": 0},
        {"image_provider_retry_attempts": 6},
        {"image_provider_retry_backoff_seconds": -1},
        {"image_provider_model": ""},
    ],
)
def test_image_provider_rejects_invalid_settings(value: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(value)
