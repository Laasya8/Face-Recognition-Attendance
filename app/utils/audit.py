"""Audit-trail helper.

``record_audit`` only stages the row in the active SQLAlchemy session; the
caller's commit persists it together with the action being audited, so the
audit trail can never contain an entry for an action that rolled back.
"""

import json

from flask_login import current_user

from app.extensions import db
from app.models.audit import AuditLog


def record_audit(action, entity=None, entity_id=None, details=None, actor=None):
    """Stage an audit entry in the current DB session.

    :param action: short verb string, e.g. ``login``, ``person.create``.
    :param entity: entity type the action targets, e.g. ``person``.
    :param entity_id: primary key of the target entity.
    :param details: JSON-serialisable context (old/new values, reasons).
    :param actor: the acting AdminUser; defaults to the logged-in user.
    """
    if actor is None and current_user is not None and current_user.is_authenticated:
        actor = current_user

    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=json.dumps(details, default=str) if details is not None else None,
    )
    db.session.add(entry)
    return entry
