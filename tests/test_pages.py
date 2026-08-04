"""Render and access-control tests for the dashboard pages."""

from app.extensions import db
from app.models import AttendanceSession, Person, utcnow

from tests.conftest import login


def make_person(code="P001", name="Ada Lovelace", thumbnail=None):
    person = Person(code=code, full_name=name, thumbnail=thumbnail)
    db.session.add(person)
    db.session.commit()
    return person


def test_persons_page_renders_with_enroll_actions(client):
    login(client)
    make_person()
    response = client.get("/persons")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ada Lovelace" in page
    assert "Add Student" in page
    assert "Enroll" in page


def test_persons_page_hides_operator_controls_from_viewer(client):
    login(client, username="viewer")
    make_person()
    response = client.get("/persons")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Add Student" not in page
    assert "create-person-form" not in page


def test_enroll_page_renders_capture_limits(client, app):
    login(client)
    person = make_person()
    response = client.get(f"/persons/{person.id}/enroll")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-min-images="5"' in page
    assert 'data-max-images="10"' in page


def test_enroll_page_forbidden_for_viewer(client):
    login(client, username="viewer")
    person = make_person()
    assert client.get(f"/persons/{person.id}/enroll").status_code == 403


def test_thumbnail_served_and_missing_thumbnail_404s(client):
    login(client)
    with_thumb = make_person(code="P001", thumbnail=b"\xff\xd8jpegbytes")
    without_thumb = make_person(code="P002", name="No Thumb")

    response = client.get(f"/persons/{with_thumb.id}/thumbnail.jpg")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"\xff\xd8jpegbytes"

    assert client.get(f"/persons/{without_thumb.id}/thumbnail.jpg").status_code == 404


def test_sessions_page_lists_sessions(client):
    login(client)
    now = utcnow()
    db.session.add(
        AttendanceSession(name="Morning", session_date=now.date(), start_time=now)
    )
    db.session.commit()

    response = client.get("/sessions")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Morning" in page
    assert "Close" in page  # operator sees the close button


def test_kiosk_without_open_session_shows_warning(client):
    login(client)
    response = client.get("/kiosk")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No open attendance session" in page


def test_kiosk_with_open_session_renders_root(client):
    login(client)
    now = utcnow()
    session = AttendanceSession(
        name="Morning", session_date=now.date(), start_time=now
    )
    db.session.add(session)
    db.session.commit()

    response = client.get("/kiosk")
    page = response.get_data(as_text=True)
    assert f'data-session-id="{session.id}"' in page


def test_kiosk_forbidden_for_viewer(client):
    login(client, username="viewer")
    assert client.get("/kiosk").status_code == 403
