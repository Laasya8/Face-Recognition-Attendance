"""API tests: auth boundaries, person management, enrollment, recognition."""

import numpy as np

from app.extensions import db
from app.models import AttendanceRecord, FaceEmbedding, Person
from app.models.audit import RecognitionLog

from tests.conftest import login, observation, unit_vector

FIVE_IMAGES = ["aW1n"] * 5  # content is irrelevant; decode_image is faked


def enroll(client, fake_vision, axis=0, code="P001", name="Test Person"):
    """Create and enroll a person whose identity is unit_vector(axis)."""
    response = client.post(
        "/api/v1/persons", json={"code": code, "full_name": name}
    )
    assert response.status_code == 201
    person_id = response.get_json()["person"]["id"]

    fake_vision([[observation(unit_vector(axis=axis))] for _ in FIVE_IMAGES])
    response = client.post(
        f"/api/v1/persons/{person_id}/enroll", json={"images": FIVE_IMAGES}
    )
    assert response.status_code == 200, response.get_json()
    return person_id


# --- auth boundaries ------------------------------------------------------


def test_api_requires_auth_with_json_401(client):
    response = client.get("/api/v1/persons")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_viewer_cannot_create_person(client):
    login(client, username="viewer")
    response = client.post(
        "/api/v1/persons", json={"code": "X1", "full_name": "Nope"}
    )
    assert response.status_code == 403


# --- persons and enrollment ----------------------------------------------


def test_create_and_list_persons(client):
    login(client)
    response = client.post(
        "/api/v1/persons",
        json={"code": "P001", "full_name": "Ada Lovelace", "group_name": "CS-A"},
    )
    assert response.status_code == 201
    body = response.get_json()["person"]
    assert body["code"] == "P001"
    assert body["is_enrolled"] is False

    response = client.post(
        "/api/v1/persons", json={"code": "P001", "full_name": "Duplicate"}
    )
    assert response.status_code == 409

    response = client.get("/api/v1/persons")
    assert [p["code"] for p in response.get_json()["persons"]] == ["P001"]


def test_enrollment_stores_samples_and_centroid(client, fake_vision):
    login(client)
    person_id = enroll(client, fake_vision)

    person = db.session.get(Person, person_id)
    assert person.is_enrolled
    assert person.thumbnail == b"jpeg"
    embeddings = person.embeddings
    assert len(embeddings) == 6  # 5 samples + 1 centroid
    centroids = [e for e in embeddings if e.is_centroid]
    assert len(centroids) == 1
    np.testing.assert_allclose(
        centroids[0].get_vector(), unit_vector(axis=0), atol=1e-6
    )


def test_enrollment_rejects_bad_images_with_details(client, fake_vision):
    login(client)
    response = client.post(
        "/api/v1/persons", json={"code": "P002", "full_name": "Two Faces"}
    )
    person_id = response.get_json()["person"]["id"]

    # Image 2 has no face, image 3 has two faces.
    fake_vision(
        [
            [observation(unit_vector())],
            [],
            [observation(unit_vector()), observation(unit_vector(axis=1))],
            [observation(unit_vector())],
            [observation(unit_vector())],
        ]
    )
    response = client.post(
        f"/api/v1/persons/{person_id}/enroll", json={"images": FIVE_IMAGES}
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "enrollment_rejected"
    assert len(error["problems"]) == 2

    person = db.session.get(Person, person_id)
    assert not person.is_enrolled
    assert len(person.embeddings) == 0


def test_enrollment_count_out_of_range(client, fake_vision):
    login(client)
    response = client.post(
        "/api/v1/persons", json={"code": "P003", "full_name": "Too Few"}
    )
    person_id = response.get_json()["person"]["id"]
    fake_vision([])
    response = client.post(
        f"/api/v1/persons/{person_id}/enroll", json={"images": ["aW1n"] * 2}
    )
    assert response.status_code == 422


def test_reenrollment_replaces_template(client, fake_vision):
    login(client)
    person_id = enroll(client, fake_vision, axis=0)

    fake_vision([[observation(unit_vector(axis=3))] for _ in FIVE_IMAGES])
    response = client.post(
        f"/api/v1/persons/{person_id}/enroll", json={"images": FIVE_IMAGES}
    )
    assert response.status_code == 200

    embeddings = db.session.execute(
        db.select(FaceEmbedding).filter_by(person_id=person_id)
    ).scalars().all()
    assert len(embeddings) == 6
    centroid = next(e for e in embeddings if e.is_centroid)
    np.testing.assert_allclose(
        centroid.get_vector(), unit_vector(axis=3), atol=1e-6
    )


# --- sessions and recognition --------------------------------------------


def open_session(client, name="Morning Lecture", **extra):
    response = client.post("/api/v1/sessions", json={"name": name, **extra})
    assert response.status_code == 201
    return response.get_json()["session"]["id"]


def test_recognize_requires_open_session(client, fake_vision):
    login(client)
    fake_vision([])
    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    assert response.status_code == 409


def test_recognize_marks_attendance_once(client, fake_vision):
    login(client)
    person_id = enroll(client, fake_vision)
    session_id = open_session(client)

    fake_vision([[observation(unit_vector(axis=0))]] * 2)

    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    body = response.get_json()
    assert body["outcome"] == "accepted"
    assert body["person"]["id"] == person_id
    assert body["attendance"]["created"] is True
    assert body["attendance"]["status"] == "present"

    # Same face again: no duplicate row.
    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    body = response.get_json()
    assert body["attendance"]["created"] is False

    records = db.session.execute(
        db.select(AttendanceRecord).filter_by(session_id=session_id)
    ).scalars().all()
    assert len(records) == 1
    assert records[0].confidence is not None

    logs = db.session.execute(db.select(RecognitionLog)).scalars().all()
    assert [log.outcome for log in logs] == ["accepted", "accepted"]


def test_recognize_unknown_face_logs_but_marks_nothing(client, fake_vision):
    login(client)
    enroll(client, fake_vision, axis=0)
    open_session(client)

    fake_vision([[observation(unit_vector(axis=7))]])
    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    body = response.get_json()
    assert body["outcome"] == "unknown"
    assert "attendance" not in body

    assert db.session.scalar(db.select(db.func.count()).select_from(AttendanceRecord)) == 0
    log = db.session.execute(db.select(RecognitionLog)).scalar_one()
    assert log.outcome == "unknown"
    assert log.person_id is None


def test_recognize_no_face(client, fake_vision):
    login(client)
    open_session(client)
    fake_vision([[]])
    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    assert response.get_json()["outcome"] == "no_face"
    assert db.session.scalar(db.select(db.func.count()).select_from(RecognitionLog)) == 0


def test_recognize_after_late_cutoff(client, fake_vision):
    login(client)
    enroll(client, fake_vision)
    session_id = open_session(client, name="Strict", late_after_minutes=0)

    # Backdate the cutoff rather than racing the clock: utcnow() ticks at
    # ~15.6 ms on Windows, so "created just now" can equal the cutoff.
    from datetime import timedelta

    from app.models import AttendanceSession, utcnow

    session = db.session.get(AttendanceSession, session_id)
    session.late_after = utcnow() - timedelta(minutes=5)
    db.session.commit()

    fake_vision([[observation(unit_vector(axis=0))]])
    response = client.post("/api/v1/recognize", json={"image": "aW1n"})
    assert response.get_json()["attendance"]["status"] == "late"


def test_closed_session_rejects_recognition(client, fake_vision):
    login(client)
    enroll(client, fake_vision)
    session_id = open_session(client)

    response = client.post(f"/api/v1/sessions/{session_id}/close")
    assert response.status_code == 200

    fake_vision([[observation(unit_vector(axis=0))]])
    response = client.post(
        "/api/v1/recognize", json={"image": "aW1n", "session_id": session_id}
    )
    assert response.status_code == 409
