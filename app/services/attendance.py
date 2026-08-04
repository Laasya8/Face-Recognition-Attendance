"""Attendance marking with duplicate suppression and late detection.

The database's UNIQUE(session_id, person_id) constraint is the source of
truth for "already marked": the pre-check here is a fast path, and the
savepoint-wrapped insert absorbs the race where two kiosk frames of the same
person commit concurrently.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AttendanceRecord, Setting, utcnow


@dataclass
class MarkResult:
    record: AttendanceRecord
    created: bool  # False when the person was already marked


def mark_attendance(session, person, confidence=None, marked_by="system"):
    """Mark ``person`` present in ``session``; idempotent per session.

    Stages the row on the current DB session; the caller commits. Arrivals
    after ``session.late_after`` are recorded as ``late``.
    """
    existing = db.session.execute(
        db.select(AttendanceRecord).filter_by(
            session_id=session.id, person_id=person.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return MarkResult(record=existing, created=False)

    now = utcnow()

    cooldown_minutes = Setting.get_int("attendance_cooldown_minutes", 0)
    if cooldown_minutes > 0:
        last_record = db.session.execute(
            db.select(AttendanceRecord)
            .where(AttendanceRecord.person_id == person.id)
            .order_by(AttendanceRecord.marked_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last_record is not None:
            if now - last_record.marked_at < timedelta(minutes=cooldown_minutes):
                return MarkResult(record=last_record, created=False)

    status = "present"
    if session.late_after is not None and now > session.late_after:
        status = "late"

    record = AttendanceRecord(
        session_id=session.id,
        person_id=person.id,
        marked_at=now,
        status=status,
        confidence=confidence,
        marked_by=marked_by,
    )

    try:
        with db.session.begin_nested():
            db.session.add(record)
    except IntegrityError:
        # Lost the race to a concurrent mark; the savepoint rollback removed
        # our row without disturbing anything else staged on the session.
        existing = db.session.execute(
            db.select(AttendanceRecord).filter_by(
                session_id=session.id, person_id=person.id
            )
        ).scalar_one()
        return MarkResult(record=existing, created=False)

    return MarkResult(record=record, created=True)
