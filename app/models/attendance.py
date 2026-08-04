"""Attendance records — one row per person per session."""

from sqlalchemy.orm import validates

from app.extensions import db
from app.models import utcnow

ATTENDANCE_STATUSES = ("present", "late", "manual")


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=False
    )
    person_id = db.Column(db.Integer, db.ForeignKey("persons.id"), nullable=False)
    marked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    status = db.Column(db.String(16), nullable=False, default="present")
    # Cosine similarity at match time; NULL for manual marks.
    confidence = db.Column(db.Float)
    # 'system' for automatic recognition, otherwise the admin username.
    marked_by = db.Column(db.String(64), nullable=False, default="system")

    session = db.relationship("AttendanceSession", back_populates="records")
    person = db.relationship("Person", back_populates="attendance_records")

    __table_args__ = (
        # Race-proof duplicate suppression: two concurrent recognitions of the
        # same person collide here and the second gets an IntegrityError.
        db.UniqueConstraint("session_id", "person_id", name="uq_attendance_once"),
        db.CheckConstraint(status.in_(ATTENDANCE_STATUSES), name="ck_attendance_status"),
        # Per-person history ("show my attendance, newest first"). The unique
        # constraint's index leads with session_id, so it cannot serve
        # person-keyed lookups.
        db.Index("ix_attendance_person_marked", "person_id", "marked_at"),
    )

    @validates("status")
    def _validate_status(self, _key, value):
        if value not in ATTENDANCE_STATUSES:
            raise ValueError(
                f"status must be one of {ATTENDANCE_STATUSES}, got {value!r}"
            )
        return value

    @validates("confidence")
    def _validate_confidence(self, _key, value):
        # Cosine similarity of unit vectors is bounded to [-1, 1]; anything
        # outside means a caller passed a raw score from the wrong scale.
        if value is not None and not -1.0 <= value <= 1.0:
            raise ValueError(f"confidence must be within [-1, 1], got {value}")
        return value

    def __repr__(self):
        return (
            f"<AttendanceRecord person={self.person_id} "
            f"session={self.session_id} {self.status}>"
        )
