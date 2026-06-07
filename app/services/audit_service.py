from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    actor_id: int | None,
    entity_type: str,
    entity_id: int | None,
    action: str,
    diff: dict | None = None,
) -> AuditLog:
    """Запись аудита создается вместе с основным действием, чтобы история не терялась."""
    entry = AuditLog(
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        diff=diff,
    )
    db.add(entry)
    return entry
