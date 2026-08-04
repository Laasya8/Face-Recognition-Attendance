"""Tests for the Student Management Module."""

# pyrefly: ignore [missing-import]
import pytest
import numpy as np
from app.extensions import db
from app.models import Person, FaceEmbedding
from tests.conftest import login, observation, unit_vector


def test_student_model_validation(app):
    # Valid year and department
    s = Person(code="S001", full_name="Ada Lovelace", department="CSE", year=2)
    assert s.department == "CSE"
    assert s.year == 2

    # Invalid year
    with pytest.raises(ValueError, match="year"):
        Person(code="S002", full_name="X", year=5)
    with pytest.raises(ValueError, match="year"):
        Person(code="S003", full_name="X", year=0)

    # Empty department is converted to None
    s2 = Person(code="S004", full_name="X", department="  ")
    assert s2.department is None


def test_api_student_crud(client):
    login(client, username="operator")

    # 1. Create Student via API
    response = client.post(
        "/api/v1/persons",
        json={
            "code": "S101",
            "full_name": "Alan Turing",
            "department": "ECE",
            "year": 3,
            "email": "alan@turing.org",
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["person"]["code"] == "S101"
    assert body["person"]["department"] == "ECE"
    assert body["person"]["year"] == 3

    person_id = body["person"]["id"]

    # 2. Update Student via API
    response = client.put(
        f"/api/v1/persons/{person_id}",
        json={
            "code": "s101-modified",
            "full_name": "Alan M. Turing",
            "department": "ECE-Robotics",
            "year": 4,
            "email": "alan.turing@ece.org",
            "is_active": True,
        },
    )
    assert response.status_code == 200
    body_update = response.get_json()
    assert body_update["person"]["code"] == "s101-modified"
    assert body_update["person"]["full_name"] == "Alan M. Turing"
    assert body_update["person"]["department"] == "ECE-Robotics"
    assert body_update["person"]["year"] == 4

    # 3. Create Face Embedding to test CASCADE delete
    person = db.session.get(Person, person_id)
    embedding = FaceEmbedding(person=person, is_centroid=True)
    embedding.set_vector(np.eye(1, 512, dtype=np.float32)[0])
    db.session.add(embedding)
    db.session.commit()

    # Verify embedding exists
    assert FaceEmbedding.query.filter_by(person_id=person_id).count() == 1

    # 4. Delete Student via API
    response = client.delete(f"/api/v1/persons/{person_id}")
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"

    # Verify student and cascade embedding are deleted
    assert db.session.get(Person, person_id) is None
    assert FaceEmbedding.query.filter_by(person_id=person_id).count() == 0


def test_dashboard_persons_search_and_filters(client):
    login(client, username="operator")

    # Add diverse students
    s1 = Person(code="S01", full_name="Ada Lovelace", department="CSE", year=2)
    s2 = Person(code="S02", full_name="Alan Turing", department="CSE", year=3)
    s3 = Person(code="S03", full_name="Grace Hopper", department="ECE", year=2)
    db.session.add_all([s1, s2, s3])
    db.session.commit()

    # 1. Test search query
    response = client.get("/persons?q=Ada")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ada Lovelace" in page
    assert "Alan Turing" not in page

    # 2. Test department filter
    response = client.get("/persons?department=CSE")
    page = response.get_data(as_text=True)
    assert "Ada Lovelace" in page
    assert "Alan Turing" in page
    assert "Grace Hopper" not in page

    # 3. Test year filter
    response = client.get("/persons?year=3")
    page = response.get_data(as_text=True)
    assert "Alan Turing" in page
    assert "Ada Lovelace" not in page

    # 4. Test combined filter
    response = client.get("/persons?department=ECE&year=2")
    page = response.get_data(as_text=True)
    assert "Grace Hopper" in page
    assert "Ada Lovelace" not in page


def test_dashboard_persons_pagination(client):
    login(client, username="operator")

    # Add 12 students with alphabetical names so they don't overlap as substrings
    # Student A, Student B, ..., Student L
    for i in range(1, 13):
        letter = chr(64 + i)  # A to L
        db.session.add(Person(code=f"S{i:03d}", full_name=f"Student {letter}"))
    db.session.commit()

    # First page (shows Student A to Student J)
    response = client.get("/persons?page=1")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Student A" in page
    assert "Student J" in page
    assert "Student K" not in page  # on next page
    assert "Student L" not in page

    # Second page (shows Student K and Student L)
    response = client.get("/persons?page=2")
    page = response.get_data(as_text=True)
    assert "Student K" in page
    assert "Student L" in page
    assert "Student A" not in page


def test_gallery_invalidated_on_delete_and_deactivate(client, fake_vision):
    login(client, username="operator")
    
    # 1. Create and enroll student
    response = client.post(
        "/api/v1/persons", json={"code": "P010", "full_name": "Test Invalidation"}
    )
    person_id = response.get_json()["person"]["id"]
    
    from tests.test_api import FIVE_IMAGES
    fake_vision([[observation(unit_vector(axis=0))] for _ in FIVE_IMAGES])
    client.post(f"/api/v1/persons/{person_id}/enroll", json={"images": FIVE_IMAGES})
    
    # Verify matches successfully
    from app.services import matcher
    res = matcher.match_embedding(unit_vector(axis=0))
    assert res.outcome == "accepted"
    assert res.person_id == person_id
    
    # 2. Deactivate student via API
    client.put(
        f"/api/v1/persons/{person_id}",
        json={
            "code": "P010",
            "full_name": "Test Invalidation",
            "is_active": False
        }
    )
    
    # Verify no longer matches in the cached gallery (without calling matcher.invalidate_gallery manually)
    res = matcher.match_embedding(unit_vector(axis=0))
    assert res.outcome == "unknown"
    
    # 3. Reactivate student via API
    client.put(
        f"/api/v1/persons/{person_id}",
        json={
            "code": "P010",
            "full_name": "Test Invalidation",
            "is_active": True
        }
    )
    res = matcher.match_embedding(unit_vector(axis=0))
    assert res.outcome == "accepted"
    
    # 4. Delete student via API
    client.delete(f"/api/v1/persons/{person_id}")
    
    # Verify no longer matches
    res = matcher.match_embedding(unit_vector(axis=0))
    assert res.outcome == "unknown"


def test_duplicate_enrollment_rejected(client, fake_vision):
    login(client, username="operator")

    # 1. Create and enroll first student with face vector 0
    res1 = client.post(
        "/api/v1/persons", json={"code": "P201", "full_name": "First Student"}
    )
    p1_id = res1.get_json()["person"]["id"]

    from tests.test_api import FIVE_IMAGES
    fake_vision([[observation(unit_vector(axis=0))] for _ in FIVE_IMAGES])
    client.post(f"/api/v1/persons/{p1_id}/enroll", json={"images": FIVE_IMAGES})

    # 2. Create second student
    res2 = client.post(
        "/api/v1/persons", json={"code": "P202", "full_name": "Second Student"}
    )
    p2_id = res2.get_json()["person"]["id"]

    # 3. Attempt to enroll second student with same face vector 0
    fake_vision([[observation(unit_vector(axis=0))] for _ in FIVE_IMAGES])
    response = client.post(f"/api/v1/persons/{p2_id}/enroll", json={"images": FIVE_IMAGES})

    # Assert that enrollment gets rejected with conflict error
    assert response.status_code == 422
    body = response.get_json()
    assert "error" in body
    assert "Face already enrolled under" in body["error"]["message"]


