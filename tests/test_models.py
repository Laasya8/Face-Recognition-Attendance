"""Model-level validation and constraint behaviour."""

import numpy as np
import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AdminUser,
    AttendanceRecord,
    AttendanceSession,
    FaceEmbedding,
    Person,
    utcnow,
)
from app.models.audit import RecognitionLog


# --- validators fire on assignment, before any DB round-trip ---------------


def test_person_rejects_blank_code_and_name(app):
    with pytest.raises(ValueError, match="code"):
        Person(code="   ", full_name="X")
    with pytest.raises(ValueError, match="full_name"):
        Person(code="P1", full_name="")


def test_person_normalises_email_and_rejects_garbage(app):
    person = Person(code="P1", full_name="X", email="  Ada@Example.COM ")
    assert person.email == "ada@example.com"
    assert Person(code="P2", full_name="X", email="  ").email is None
    with pytest.raises(ValueError, match="email"):
        Person(code="P3", full_name="X", email="not-an-email")


def test_admin_username_normalised_and_role_checked(app):
    user = AdminUser(username="  Alice ", role="admin")
    assert user.username == "alice"
    with pytest.raises(ValueError, match="at least 3"):
        AdminUser(username="ab", role="admin")
    with pytest.raises(ValueError, match="role"):
        AdminUser(username="carol", role="superuser")


def test_attendance_status_and_confidence_bounds(app):
    with pytest.raises(ValueError, match="status"):
        AttendanceRecord(status="absent")
    with pytest.raises(ValueError, match="confidence"):
        AttendanceRecord(status="present", confidence=45.0)
    record = AttendanceRecord(status="late", confidence=0.62)
    assert record.confidence == 0.62


def test_session_and_recognition_validators(app):
    with pytest.raises(ValueError, match="name"):
        AttendanceSession(name=" ", session_date=utcnow().date())
    with pytest.raises(ValueError, match="status"):
        AttendanceSession(
            name="X", session_date=utcnow().date(), status="paused"
        )
    with pytest.raises(ValueError, match="outcome"):
        RecognitionLog(outcome="maybe")


def test_embedding_quality_score_bounds(app):
    with pytest.raises(ValueError, match="quality_score"):
        FaceEmbedding(quality_score=1.5)


def test_embedding_vector_shape_and_norm_checks(app):
    embedding = FaceEmbedding()
    with pytest.raises(ValueError, match="512-d"):
        embedding.set_vector(np.ones(10, dtype=np.float32))
    with pytest.raises(ValueError, match="norm"):
        embedding.set_vector(np.zeros(512, dtype=np.float32))


# --- DB-level constraints are the backstop --------------------------------


def test_duplicate_person_code_hits_unique_constraint(app):
    db.session.add(Person(code="P1", full_name="A"))
    db.session.commit()
    db.session.add(Person(code="P1", full_name="B"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleting_person_cascades_to_embeddings(app):
    person = Person(code="P1", full_name="A")
    embedding = FaceEmbedding(person=person, is_centroid=True)
    embedding.set_vector(np.eye(1, 512, dtype=np.float32)[0])
    db.session.add_all([person, embedding])
    db.session.commit()

    db.session.delete(person)
    db.session.commit()
    assert (
        db.session.scalar(db.select(db.func.count()).select_from(FaceEmbedding))
        == 0
    )


def test_same_session_name_allowed_on_different_dates(app):
    from datetime import date

    db.session.add_all(
        [
            AttendanceSession(
                name="Morning", session_date=date(2026, 8, 1), start_time=utcnow()
            ),
            AttendanceSession(
                name="Morning", session_date=date(2026, 8, 2), start_time=utcnow()
            ),
        ]
    )
    db.session.commit()  # no IntegrityError: uniqueness is (name, date)
