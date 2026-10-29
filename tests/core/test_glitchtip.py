from unittest.mock import patch

from vashfindir.core.config import Settings
from vashfindir.core.glitchtip import init_glitchtip


def test_init_glitchtip_skipped_without_dsn() -> None:
    settings = Settings(glitchtip_dsn="")
    with patch("vashfindir.core.glitchtip.sentry_sdk") as mock_sentry:
        init_glitchtip(settings)
        mock_sentry.init.assert_not_called()


def test_init_glitchtip_initializes_with_dsn() -> None:
    settings = Settings(
        glitchtip_dsn="https://key@glitchtip.example.com/1",
        glitchtip_environment="staging",
        glitchtip_traces_sample_rate=0.5,
    )
    with patch("vashfindir.core.glitchtip.sentry_sdk") as mock_sentry:
        init_glitchtip(settings)
        mock_sentry.init.assert_called_once_with(
            dsn="https://key@glitchtip.example.com/1",
            environment="staging",
            traces_sample_rate=0.5,
        )


def test_init_glitchtip_uses_defaults() -> None:
    settings = Settings(glitchtip_dsn="https://key@glitchtip.example.com/1")
    with patch("vashfindir.core.glitchtip.sentry_sdk") as mock_sentry:
        init_glitchtip(settings)
        mock_sentry.init.assert_called_once_with(
            dsn="https://key@glitchtip.example.com/1",
            environment="production",
            traces_sample_rate=0.0,
        )
