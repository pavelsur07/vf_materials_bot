import json
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from vashfindir.db.models import AuditLog


def record_change(
    session: AsyncSession,
    actor: int,
    entity: str,
    entity_id: str | int,
    old: Mapping[str, object],
    new: Mapping[str, object],
) -> None:
    changes = {
        field: {"old": old.get(field), "new": new.get(field)}
        for field in old.keys() | new.keys()
        if old.get(field) != new.get(field)
    }
    if changes:
        session.add(
            AuditLog(
                actor_tg_id=actor,
                entity=entity,
                entity_id=str(entity_id),
                changes=json.dumps(changes, ensure_ascii=False, default=str),
            )
        )
