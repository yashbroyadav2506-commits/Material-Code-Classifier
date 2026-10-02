"""Audit logging helper."""

from ..models import AuditLog


def log(db, action: str, entity: str = "", entity_id: str = "",
        old=None, new=None, performed_by: str = "system"):
    entry = AuditLog(
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        performed_by=performed_by,
        old_value=old or {},
        new_value=new or {},
    )
    db.add(entry)
    return entry