import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, LeadMagnet
from vashfindir.domain.attribution.dto import StartRequest
from vashfindir.domain.attribution.queries import DateWindow
from vashfindir.domain.attribution.settings import AttributionPreferences
from vashfindir.domain.attribution.touches import register_touch

MOSCOW = ZoneInfo("Europe/Moscow")


def rows(raw: bytes) -> list[list[str]]:
    assert raw.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(StringIO(raw.decode("utf-8-sig"))))


async def test_links_csv_contract(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.exports import export_links

    magnet = LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Checklist")
    session.add(magnet)
    await session.flush()
    session.add(
        AttributionLink(
            code="dds_001",
            lead_magnet_id=magnet.id,
            utm_source="tg",
            utm_medium="post",
            utm_campaign="offer",
            placement='Канал, "новости"',
            created_by=7,
            created_at=datetime(2026, 11, 21, 22, 0),
            period_start=date(2026, 11, 22),
            budget=Decimal("100.25"),
        )
    )
    await session.commit()
    report = b"".join(
        [
            chunk
            async for chunk in export_links(
                session,
                DateWindow(start=date(2026, 11, 22), end=date(2026, 11, 22)),
                MOSCOW,
            )
        ]
    )
    assert rows(report) == [
        [
            "code",
            "magnet_prefix",
            "magnet_name",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "placement",
            "period_start",
            "period_end",
            "budget",
            "status",
            "created_at",
        ],
        [
            "dds_001",
            "dds",
            "ДДС",
            "tg",
            "post",
            "offer",
            "",
            "",
            'Канал, "новости"',
            "2026-11-22 00:00:00",
            "",
            "100.25",
            "active",
            "2026-11-22 01:00:00",
        ],
    ]


async def test_touches_csv_excludes_tests_and_preserves_raw_payload(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.exports import export_touches

    now = datetime(2026, 11, 21, 22, 0)
    await register_touch(
        session,
        StartRequest(tg_id=12, first_name="Иван", username="user", payload="bad,code"),
        now=now,
    )
    await register_touch(
        session,
        StartRequest(tg_id=13, first_name="Тест"),
        AttributionPreferences(test_ids=[13]),
        now=now,
    )
    window = DateWindow()
    report = b"".join([chunk async for chunk in export_touches(session, window, MOSCOW)])
    assert rows(report) == [
        [
            "touch_id",
            "created_at",
            "tg_id",
            "username",
            "code",
            "raw_payload",
            "code_status",
            "magnet_prefix",
            "magnet_source",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "is_new_user",
            "magnet_delivered",
            "bitrix_lead_id",
        ],
        [
            "1",
            "2026-11-22 01:00:00",
            "12",
            "user",
            "unknown",
            "bad,code",
            "unknown",
            "",
            "",
            "unknown",
            "",
            "",
            "",
            "",
            "1",
            "0",
            "",
        ],
    ]
    report = b"".join(
        [chunk async for chunk in export_touches(session, window, MOSCOW, include_test=True)]
    )
    assert rows(report)[2][2:7] == ["13", "", "direct", "", "direct"]
