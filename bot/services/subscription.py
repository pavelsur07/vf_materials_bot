from enum import StrEnum


class SubscriptionStatus(StrEnum):
    SUBSCRIBED = "subscribed"
    NOT_SUBSCRIBED = "not_subscribed"
    CHECK_ERROR = "check_error"


_SUBSCRIBED_STATUSES = {"member", "administrator", "creator", "restricted"}
_NOT_SUBSCRIBED_STATUSES = {"left", "kicked"}


def classify_member_status(status: str | None) -> SubscriptionStatus:
    if status in _SUBSCRIBED_STATUSES:
        return SubscriptionStatus.SUBSCRIBED
    if status in _NOT_SUBSCRIBED_STATUSES:
        return SubscriptionStatus.NOT_SUBSCRIBED
    return SubscriptionStatus.CHECK_ERROR
