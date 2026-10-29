from pydantic import BaseModel

from vashfindir.domain.subscription import SubscriptionStatus


class OnboardingContext(BaseModel):
    tg_id: int
    username: str | None
    first_name: str | None


class OnboardingResult(BaseModel):
    status: SubscriptionStatus
    text: str
    channel_url: str
    leadmagnet_url: str
    is_retry: bool
