"""Shared fixtures.

The suite runs against the in-memory testing config and a fake vision layer
(``fake_vision``) — no model download, no cv2. Real InsightFace inference is
covered by scripts/engine_check.py, not the unit suite.
"""

import numpy as np
import pytest

from app import create_app
from app.extensions import db as _db
from app.models import AdminUser, Setting
from app.services import face_engine, matcher
from app.services.face_engine import FaceObservation


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        for key, value in app.config["DEFAULT_SETTINGS"].items():
            _db.session.add(Setting(key=key, value=value))

        operator = AdminUser(username="operator", role="operator")
        operator.set_password("password123")
        viewer = AdminUser(username="viewer", role="viewer")
        viewer.set_password("password123")
        _db.session.add_all([operator, viewer])
        _db.session.commit()

        matcher.invalidate_gallery()
        yield app

        _db.session.remove()
        _db.drop_all()
    matcher.invalidate_gallery()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username="operator", password="password123"):
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def unit_vector(dim=512, axis=0):
    vector = np.zeros(dim, dtype=np.float32)
    vector[axis] = 1.0
    return vector


def blended_vector(similarity, axis_a=0, axis_b=1, dim=512):
    """Unit vector whose dot product with unit_vector(axis=axis_a) is exactly
    ``similarity``."""
    vector = np.zeros(dim, dtype=np.float32)
    vector[axis_a] = similarity
    vector[axis_b] = np.sqrt(1.0 - similarity**2)
    return vector


class FakeEngine:
    """Returns queued observation lists, one list per analyze() call."""

    def __init__(self, batches):
        self.batches = list(batches)

    def analyze(self, _image):
        if not self.batches:
            raise AssertionError("FakeEngine ran out of queued batches")
        return self.batches.pop(0)


def observation(embedding, det_score=0.95):
    return FaceObservation(
        embedding=np.asarray(embedding, dtype=np.float32),
        bbox=(10, 10, 110, 110),
        det_score=det_score,
    )


@pytest.fixture()
def fake_vision(monkeypatch):
    """Replace the vision layer; returns a setter for queued analyze results."""

    def install(batches):
        engine = FakeEngine(batches)
        monkeypatch.setattr(face_engine, "get_engine", lambda: engine)
        monkeypatch.setattr(
            face_engine,
            "decode_image",
            lambda data: np.random.randint(100, 150, (240, 320, 3), dtype=np.uint8),
        )
        monkeypatch.setattr(
            face_engine, "make_thumbnail", lambda image, bbox, size=112: b"jpeg"
        )
        return engine

    return install
