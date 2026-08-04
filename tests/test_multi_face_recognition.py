"""Integration tests for multi-face recognition and configuration settings."""

from app.extensions import db
from app.models import Person, AttendanceRecord, Setting
from tests.conftest import login, observation, unit_vector
from tests.test_api import open_session


def test_multi_face_recognition_and_marking(client, fake_vision):
    login(client)
    
    # 1. Enroll two separate students
    p1 = Person(code="M01", full_name="Student One")
    p2 = Person(code="M02", full_name="Student Two")
    db.session.add_all([p1, p2])
    db.session.commit()

    # Create face centroids for both students
    from app.models import FaceEmbedding
    from app.services.face_engine import MODEL_NAME
    
    emb1 = FaceEmbedding(person=p1, is_centroid=True, quality_score=0.9, model_name=MODEL_NAME)
    emb1.set_vector(unit_vector(axis=0)) # vector in direction 0
    emb2 = FaceEmbedding(person=p2, is_centroid=True, quality_score=0.9, model_name=MODEL_NAME)
    emb2.set_vector(unit_vector(axis=1)) # vector in direction 1
    
    db.session.add_all([emb1, emb2])
    db.session.commit()
    
    # Invalidate gallery so it reloads the new centroids
    from app.services import matcher
    matcher.invalidate_gallery()

    session_id = open_session(client)

    # 2. Mock two face detections in a single frame
    obs1 = observation(unit_vector(axis=0)) # matches Student One
    obs2 = observation(unit_vector(axis=1)) # matches Student Two
    fake_vision([[obs1, obs2]])

    # 3. Call recognition API
    response = client.post("/api/v1/recognize", json={"image": "aW1n", "session_id": session_id})
    assert response.status_code == 200
    body = response.get_json()

    assert body["faces_detected"] == 2
    assert body["outcome"] == "accepted" # primary face is accepted
    
    # Verify results list
    results = body["results"]
    assert len(results) == 2
    assert results[0]["person"]["code"] == "M01"
    assert results[0]["attendance"]["created"] is True
    assert results[1]["person"]["code"] == "M02"
    assert results[1]["attendance"]["created"] is True

    # Check database: both students marked present
    records = AttendanceRecord.query.filter_by(session_id=session_id).all()
    assert len(records) == 2
    marked_ids = {r.person_id for r in records}
    assert marked_ids == {p1.id, p2.id}


def test_configurable_similarity_threshold(client, fake_vision):
    login(client)
    
    p = Person(code="M03", full_name="Student Three")
    db.session.add(p)
    db.session.commit()

    from app.models import FaceEmbedding
    from app.services.face_engine import MODEL_NAME
    
    emb = FaceEmbedding(person=p, is_centroid=True, quality_score=0.9, model_name=MODEL_NAME)
    emb.set_vector(unit_vector(axis=0))
    db.session.add(emb)
    db.session.commit()

    from app.services import matcher
    matcher.invalidate_gallery()

    session_id = open_session(client)

    # Set very high acceptance threshold (0.99)
    Setting.set("similarity_threshold_accept", "0.99")
    db.session.commit()

    obs = observation(unit_vector(axis=0)) # normally 100% match
    fake_vision([[obs]])

    # When similarity is 1.0, and accept is 0.99, it should pass
    response = client.post("/api/v1/recognize", json={"image": "aW1n", "session_id": session_id})
    assert response.get_json()["outcome"] == "accepted"

    # Set threshold above 1.0 (impossible match)
    Setting.set("similarity_threshold_accept", "1.05")
    Setting.set("similarity_threshold_review", "0.99")
    db.session.commit()

    fake_vision([[obs]])
    response = client.post("/api/v1/recognize", json={"image": "aW1n", "session_id": session_id})
    # Since similarity is 1.0 (which is < 1.05 and >= 0.99), it is below_threshold
    assert response.get_json()["outcome"] == "below_threshold"
