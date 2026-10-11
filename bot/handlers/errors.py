import logging

import sentry_sdk
from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> None:
    logger.exception("Unhandled error while processing update %s", event.update.update_id)
    if event.exception:
        sentry_sdk.capture_exception(event.exception)
