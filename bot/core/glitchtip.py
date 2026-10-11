import sentry_sdk

from bot.core.config import Settings


def init_glitchtip(settings: Settings) -> None:
    """Initialize GlitchTip/Sentry SDK if DSN is configured."""
    if not settings.glitchtip_dsn:
        return

    sentry_sdk.init(
        dsn=settings.glitchtip_dsn,
        environment=settings.glitchtip_environment,
        traces_sample_rate=settings.glitchtip_traces_sample_rate,
    )
