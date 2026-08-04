"""Attendance sessions — the unit attendance is recorded against."""

from sqlalchemy.orm import validates

from app.extensions import db
from app.models import utcnow

SESSION_STATUSES = ("open", "closed")


class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    session_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, default=utcnow)
    end_time = db.Column(db.DateTime)
    # Arrivals after this instant are marked 'late' instead of 'present'.
    late_after = db.Column(db.DateTime)
    status = db.Column(db.String(16), nullable=False, default="open")
    created_by_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"))

    # Branch / year context — nullable so existing sessions remain valid.
    # department: the branch this class is for, e.g. "CSE", "ECE", "MECH"
    # year: academic year targeted (1–4); NULL means not year-specific
    department = db.Column(db.String(80), index=True)
    year = db.Column(db.Integer, index=True)

    created_by = db.relationship("AdminUser")
    records = db.relationship(
        "AttendanceRecord", back_populates="session", lazy="dynamic",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    recognition_logs = db.relationship(
        "RecognitionLog", backref="session", lazy="dynamic",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        # Allow "CS301 for CSE" and "CS301 for ECE" as separate sessions on the same day.
        db.UniqueConstraint("name", "department", "session_date", name="uq_session_name_dept_date"),
        db.CheckConstraint(status.in_(SESSION_STATUSES), name="ck_session_status"),
    )

    @validates("name")
    def _validate_name(self, _key, value):
        if value is None or not value.strip():
            raise ValueError("session name must be a non-empty string")
        return value.strip()

    @validates("status")
    def _validate_status(self, _key, value):
        if value not in SESSION_STATUSES:
            raise ValueError(
                f"status must be one of {SESSION_STATUSES}, got {value!r}"
            )
        return value

    @validates("department")
    def _validate_department(self, _key, value):
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @validates("year")
    def _validate_year(self, _key, value):
        if value is None or value == "":
            return None
        try:
            val = int(value)
        except (ValueError, TypeError):
            raise ValueError("year must be an integer")
        if val < 1 or val > 4:
            raise ValueError("year must be between 1 and 4")
        return val

    @property
    def is_open(self):
        return self.status == "open"

    def __repr__(self):
        dept = f" [{self.department}]" if self.department else ""
        year = f" Y{self.year}" if self.year else ""
        return f"<AttendanceSession {self.name}{dept}{year} {self.session_date} ({self.status})>"
