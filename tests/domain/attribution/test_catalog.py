import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db import models


async def test_codes_use_one_sequence_and_normalized_tags(session: AsyncSession) -> None:
    from vashfindir.domain.attribution.catalog import create_link
    from vashfindir.domain.attribution.dto import LinkInput

    first = models.LeadMagnet(prefix="dds", name="ДДС", content_type="text", message="Текст")
    second = models.LeadMagnet(prefix="opiu", name="ОПиУ", content_type="text", message="Текст")
    session.add_all(
        [
            first,
            second,
            models.DictValue(dict="source", value="tg", label="Telegram"),
            models.DictValue(dict="medium", value="post", label="Публикация"),
        ]
    )
    await session.commit()

    def source(magnet_id: int) -> LinkInput:
        return LinkInput(
            lead_magnet_id=magnet_id,
            utm_source="tg",
            utm_medium="post",
            utm_campaign="  SUMMER Offer ",
            placement="Канал",
            utm_content="New Ad",
        )

    async with session.begin():
        one = await create_link(session, source(first.id), actor=123)
        two = await create_link(session, source(second.id), actor=123)
    assert (one.code, two.code, one.utm_campaign, one.utm_content) == (
        "dds_001",
        "opiu_002",
        "summer_offer",
        "new_ad",
    )
    assert len((await session.scalars(select(models.AuditLog))).all()) == 2


@pytest.mark.parametrize("value", ["Яндекс", "ad!"])
def test_campaign_rejects_non_latin_values(value: str) -> None:
    from pydantic import ValidationError

    from vashfindir.domain.attribution.dto import LinkInput

    with pytest.raises(ValidationError):
        LinkInput(
            lead_magnet_id=1,
            utm_source="tg",
            utm_medium="post",
            utm_campaign=value,
            placement="Канал",
        )


@pytest.mark.parametrize("value", [None, "Kanal", "Канал", "tg-ad"])
def test_dictionary_validation_reports_invalid_form_values(value: object) -> None:
    from pydantic import ValidationError

    from vashfindir.domain.attribution.dto import DictValueInput

    with pytest.raises(ValidationError):
        DictValueInput.model_validate({"value": value, "label": "Канал"})
