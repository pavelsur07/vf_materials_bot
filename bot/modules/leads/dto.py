from pydantic import BaseModel, Field


class LeadNotificationIn(BaseModel):
    """Notification text built by the site. The bot relays it into Telegram as-is."""

    text: str = Field(min_length=1, max_length=4000)
