"""Enrollees — the people whose attendance is tracked."""

import re

from sqlalchemy.orm import validates

from app.extensions import db
from app.models import utcnow

# Deliberately loose: just "something@something.something". Real validation
# happens when mail is actually sent; this only catches obvious typos.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Person(db.Model):
    __tablename__ = "persons"

    id = db.Column(db.Integer, primary_key=True)
    # External identifier: roll number / employee ID.
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    # Class / department / team — free-form grouping used by reports.
    group_name = db.Column(db.String(80), index=True)
    department = db.Column(db.String(80), index=True)
    year = db.Column(db.Integer, index=True)
    email = db.Column(db.String(120))
    # Small JPEG avatar for the UI only. Recognition never touches it; the
    # biometric data lives exclusively in face_embeddings.
    thumbnail = db.Column(db.LargeBinary)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # NULL means "created but not yet enrolled".
    enrolled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # delete-orphan + passive_deletes: deleting a Person purges their
    # biometric templates via the DB-level ON DELETE CASCADE.
    embeddings = db.relationship(
        "FaceEmbedding",
        back_populates="person",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    source_images = db.relationship(
        "PersonSourceImage",
        back_populates="person",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    attendance_records = db.relationship(
        "AttendanceRecord", back_populates="person", lazy="dynamic"
    )

    @validates("code", "full_name")
    def _validate_required_text(self, key, value):
        if value is None or not value.strip():
            raise ValueError(f"Person.{key} must be a non-empty string")
        value = value.strip()
        limit = getattr(type(self), key).type.length
        if len(value) > limit:
            raise ValueError(f"Person.{key} exceeds {limit} characters")
        return value

    @validates("email")
    def _validate_email(self, _key, value):
        if value is None or not value.strip():
            return None  # store NULL, never empty string
        value = value.strip().lower()
        if not _EMAIL_PATTERN.match(value):
            raise ValueError(f"invalid email address: {value!r}")
        return value

    @validates("department")
    def _validate_department(self, _key, value):
        if value is None or not value.strip():
            return None
        value = value.strip()
        if len(value) > 80:
            raise ValueError("department exceeds 80 characters")
        return value

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
    def is_enrolled(self):
        return self.enrolled_at is not None

    def __repr__(self):
        return f"<Person {self.code} {self.full_name!r}>"


class PersonSourceImage(db.Model):
    __tablename__ = "person_source_images"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(
        db.Integer,
        db.ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Encrypted JPEG bytes
    encrypted_data = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    person = db.relationship("Person", back_populates="source_images")
