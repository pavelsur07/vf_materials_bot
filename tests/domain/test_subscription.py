import pytest

from vashfindir.domain.subscription import SubscriptionStatus, classify_member_status


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("member", SubscriptionStatus.SUBSCRIBED),
        ("administrator", SubscriptionStatus.SUBSCRIBED),
        ("creator", SubscriptionStatus.SUBSCRIBED),
        ("restricted", SubscriptionStatus.SUBSCRIBED),
        ("left", SubscriptionStatus.NOT_SUBSCRIBED),
        ("kicked", SubscriptionStatus.NOT_SUBSCRIBED),
    ],
)
def test_classify_member_status_known(status: str, expected: SubscriptionStatus) -> None:
    assert classify_member_status(status) == expected


def test_classify_member_status_unknown() -> None:
    assert classify_member_status("unknown") == SubscriptionStatus.CHECK_ERROR


def test_classify_member_status_none() -> None:
    assert classify_member_status(None) == SubscriptionStatus.CHECK_ERROR
