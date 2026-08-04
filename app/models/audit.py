"""Audit trail and recognition diagnostics."""

from sqlalchemy.orm import validates

from app.extensions import db
from app.models import utcnow

RECOGNITION_OUTCOMES = ("accepted", "below_threshold", "unknown")


class AuditLog(db.Model):
    """Who did what: logins, enrollments, manual corrections, purges."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"))
    action = db.Column(db.String(64), nullable=False, index=True)
    # e.g. entity='person', entity_id=42
    entity = db.Column(db.String(32))
    entity_id = db.Column(db.Integer)
    # JSON-encoded context (old/new values, reasons).
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("AdminUser")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id}>"


class RecognitionLog(db.Model):
    """Every match attempt, kept for threshold calibration and review.

    Pruned by a retention job; this table grows fastest.
    """

    __tablename__ = "recognition_logs"

    id = db.Column(db.Integer, primary_key=True)
    # Indexed: threshold calibration and the review queue both filter by
    # session, and this table grows too fast for scans.
    session_id = db.Column(
        db.Integer, db.ForeignKey("attendance_sessions.id"), index=True
    )
    # NULL when the face matched nobody in the gallery.
    person_id = db.Column(db.Integer, db.ForeignKey("persons.id"))
    similarity = db.Column(db.Float)
    outcome = db.Column(db.String(24), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    __table_args__ = (
        db.CheckConstraint(
            outcome.in_(RECOGNITION_OUTCOMES), name="ck_recognition_outcome"
        ),
    )

    @validates("outcome")
    def _validate_outcome(self, _key, value):
        if value not in RECOGNITION_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {RECOGNITION_OUTCOMES}, got {value!r}"
            )
        return value

    def __repr__(self):
        return f"<RecognitionLog {self.outcome} sim={self.similarity}>"
