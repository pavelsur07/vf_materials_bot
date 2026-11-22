from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, LeadMagnet, Touch, User


async def test_first_touch_is_preserved_and_duplicates_do_not_move_last(
    session: AsyncSession,
) -> None:
    from vashfindir.domain.attribution.dto import StartRequest
    from vashfindir.domain.attribution.touches import register_touch

    now = datetime(2026, 11, 22, 12)
    request = StartRequest(tg_id=765, first_name="Иван")
    first = await register_touch(session, request, now=now)
    second = await register_touch(
        session,
        request.model_copy(update={"payload": "unknown_019"}),
        now=now + timedelta(minutes=1),
    )
    duplicate = await register_touch(session, request, now=now + timedelta(minutes=2))
    later = await register_touch(session, request, now=now + timedelta(minutes=10))
    user = await session.get(User, 1)
    assert user is not None
    assert (first.touch_id, duplicate.touch_id, user.first_touch_id) == (1, 1, 1)
    assert (second.touch_id, later.touch_id, user.last_touch_id) == (2, 3, 3)
    assert (await session.get(Touch, 1)).is_new_user
    assert not (await session.get(Touch, 3)).is_new_user
    assert user.last_seen_at == now + timedelta(minutes=10)


@pytest.mark.parametrize(
    ("payload", "status", "magnet_source"),
    [
        (None, "direct", None),
        ("dds_001", "ok", "link"),
        ("dds_002", "unknown", "prefix"),
        ("dds_!", "unknown", None),
        ("dds_" + "8" * 61, "unknown", None),
    ],
)
async def test_payload_is_classified_before_delivery(
    session: AsyncSession, payload: str | None, status: str, magnet_source: str | None
) -> None:
    from vashfindir.domain.attribution.dto import StartRequest
    from vashfindir.domain.attribution.touches import register_touch

    magnet = LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Текст")
    session.add(magnet)
    await session.flush()
    session.add(
        AttributionLink(
            code="dds_001",
            lead_magnet_id=magnet.id,
            utm_source="tg",
            utm_medium="post",
            utm_campaign="offer",
            placement="Канал",
            status="archived",
            created_by=7,
        )
    )
    await session.commit()
    result = await register_touch(
        session, StartRequest(tg_id=765, first_name="Иван", payload=payload)
    )
    touch = await session.get(Touch, result.touch_id)
    assert (touch.raw_payload, touch.code_status, touch.magnet_source) == (
        payload[:64] if payload else None,
        status,
        magnet_source,
    )
    assert (touch.utm_source, touch.utm_medium, touch.bitrix_status) == (
        "tg" if status == "ok" else status,
        "post" if status == "ok" else None,
        "pending",
    )
