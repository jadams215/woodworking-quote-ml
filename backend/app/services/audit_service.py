"""Audit logging service for tracking all system mutations.

Maps to the AuditLog model defined in app.models.audit.  The caller
(service layer) is responsible for transaction management -- this module
only adds records to the session and flushes so the generated ID is
available immediately.

Column mapping (spec name -> actual model column):
    user_id       -> performed_by_id  (Integer FK to users.id, nullable)
    old_values    -> old_value_json   (Text, JSON-serialized)
    new_values    -> new_value_json   (Text, JSON-serialized)
    created_at    -> performed_at     (DateTime, server_default)
    entity_id     -> entity_id        (Integer)
"""

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def _serialize(value: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serialize a dict to a JSON string for the Text column, or None."""
    if value is None:
        return None
    return json.dumps(value, default=str)


def log_action(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int,
    performed_by_id: Optional[int] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """
    Record an audit log entry.

    Args:
        db: Database session (caller manages commit/rollback).
        action: What happened -- created, updated, deleted, status_changed,
                price_changed, locked, login, login_failed, etc.
        entity_type: Affected entity kind -- quote, customer, catalog,
                     price_book, user, etc.
        entity_id: Primary key of the affected entity.
        performed_by_id: users.id of the actor, or None for system actions.
        old_values: Previous state (for updates / deletes).  Serialized to
                    JSON text for storage.
        new_values: New state (for creates / updates).  Serialized to JSON
                    text for storage.

    Returns:
        The created AuditLog entry (with id populated after flush).
    """
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        performed_by_id=performed_by_id,
        old_value_json=_serialize(old_values),
        new_value_json=_serialize(new_values),
    )
    db.add(entry)
    db.flush()  # Populate id; caller owns the transaction.
    logger.info(
        "audit: action=%s entity=%s/%s by_user=%s",
        action,
        entity_type,
        entity_id,
        performed_by_id,
    )
    return entry


def get_audit_trail(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    limit: int = 50,
) -> list[AuditLog]:
    """Get the audit trail for a specific entity, most recent first."""
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        .order_by(AuditLog.performed_at.desc())
        .limit(min(limit, 200))
        .all()
    )


def get_user_activity(
    db: Session,
    *,
    user_id: int,
    limit: int = 50,
) -> list[AuditLog]:
    """Get recent activity performed by a specific user."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.performed_by_id == user_id)
        .order_by(AuditLog.performed_at.desc())
        .limit(min(limit, 200))
        .all()
    )
