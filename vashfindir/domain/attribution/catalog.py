from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AttributionLink, DictValue, LeadMagnet
from vashfindir.domain.attribution.audit import record_change
from vashfindir.domain.attribution.dto import (
    UTM_FIELDS,
    Dictionary,
    DictValueInput,
    LinkChanges,
    LinkInput,
    MagnetInput,
    NewMagnetInput,
)


class CatalogError(ValueError):
    pass


class DuplicateLink(CatalogError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Такая ссылка уже есть: {code}. Использовать её?")


def active_magnets() -> Select[tuple[LeadMagnet]]:
    return (
        select(LeadMagnet)
        .where(LeadMagnet.is_active.is_(True))
        .order_by(LeadMagnet.sort, LeadMagnet.id)
    )


async def save_magnet(
    session: AsyncSession,
    data: MagnetInput,
    *,
    actor: int,
    magnet: LeadMagnet | None = None,
) -> LeadMagnet:
    values = data.model_dump(exclude={"prefix"})
    old: dict[str, object] = {}
    if magnet is None:
        if not isinstance(data, NewMagnetInput):
            raise CatalogError("Укажите префикс материала.")
        magnet = LeadMagnet(prefix=data.prefix, **values)
        session.add(magnet)
        values["prefix"] = data.prefix
    else:
        old = {key: getattr(magnet, key) for key in values}
        for key, value in values.items():
            setattr(magnet, key, value)
    await session.flush()
    record_change(session, actor, "lead_magnets", magnet.id, old, values)
    return magnet


async def save_dict_value(
    session: AsyncSession,
    kind: Dictionary,
    data: DictValueInput,
    *,
    actor: int,
    entry: DictValue | None = None,
) -> DictValue:
    values = data.model_dump()
    old: dict[str, object] = {}
    if entry is None:
        entry = DictValue(dict=kind, **values)
        session.add(entry)
    else:
        values.pop("value")
        old = {key: getattr(entry, key) for key in values}
        for key, value in values.items():
            setattr(entry, key, value)
    await session.flush()
    record_change(session, actor, "dict_values", entry.id, old, values)
    return entry


async def create_link(
    session: AsyncSession, data: LinkInput, *, actor: int, confirm_duplicate: bool = False
) -> AttributionLink:
    # Reserve SQLite's writer before reading the sequence and testing for duplicates.
    await session.execute(
        update(LeadMagnet)
        .where(LeadMagnet.id == data.lead_magnet_id)
        .values(id=LeadMagnet.id, updated_at=LeadMagnet.updated_at)
    )
    magnet = await session.get(LeadMagnet, data.lead_magnet_id, populate_existing=True)
    if magnet is None or not magnet.is_active:
        raise CatalogError("Выберите активный лид-магнит.")
    for kind, value in (("source", data.utm_source), ("medium", data.utm_medium)):
        entry = await session.scalar(
            select(DictValue.id).where(
                DictValue.dict == kind, DictValue.value == value, DictValue.is_active.is_(True)
            )
        )
        if entry is None:
            raise CatalogError("Выберите активные источник и канал из справочников.")

    duplicate = await session.scalar(
        select(AttributionLink.code)
        .where(
            AttributionLink.lead_magnet_id == magnet.id,
            AttributionLink.status == "active",
            *(getattr(AttributionLink, field) == getattr(data, field) for field in UTM_FIELDS),
        )
        .order_by(AttributionLink.id)
        .limit(1)
    )
    if duplicate and (not confirm_duplicate or not data.comment):
        raise DuplicateLink(duplicate)

    next_id = (await session.scalar(select(func.max(AttributionLink.id))) or 0) + 1
    code = f"{magnet.prefix}_{next_id:03d}"
    values = data.model_dump()
    link = AttributionLink(id=next_id, code=code, created_by=actor, **values)
    session.add(link)
    await session.flush()
    record_change(session, actor, "links", link.id, {}, {**values, "code": code})
    return link


async def update_link(
    session: AsyncSession, link: AttributionLink, data: LinkChanges, *, actor: int
) -> None:
    values = data.model_dump(include=set(LinkChanges.model_fields))
    old = {key: getattr(link, key) for key in values}
    for key, value in values.items():
        setattr(link, key, value)
    record_change(session, actor, "links", link.id, old, values)
