"""Matcher outcomes across the accept/review/unknown threshold bands."""

import pytest

from app.extensions import db
from app.models import FaceEmbedding, Person
from app.services import matcher

from tests.conftest import blended_vector, unit_vector


@pytest.fixture()
def enrolled_person(app):
    person = Person(code="P001", full_name="Test Person")
    db.session.add(person)
    centroid = FaceEmbedding(person=person, is_centroid=True)
    centroid.set_vector(unit_vector(axis=0))
    db.session.add(centroid)
    db.session.commit()
    matcher.invalidate_gallery()
    return person


def test_empty_gallery_returns_unknown(app):
    result = matcher.match_embedding(unit_vector())
    assert result.outcome == "unknown"
    assert result.person_id is None
    assert result.similarity is None


def test_identical_vector_is_accepted(enrolled_person):
    result = matcher.match_embedding(unit_vector(axis=0))
    assert result.outcome == "accepted"
    assert result.person_id == enrolled_person.id
    assert result.similarity == pytest.approx(1.0)


def test_review_band_is_below_threshold(enrolled_person):
    # Dot product 0.40 sits between review (0.35) and accept (0.45).
    result = matcher.match_embedding(blended_vector(0.40))
    assert result.outcome == "below_threshold"
    assert result.person_id == enrolled_person.id
    assert result.similarity == pytest.approx(0.40, abs=1e-6)


def test_dissimilar_vector_is_unknown(enrolled_person):
    result = matcher.match_embedding(unit_vector(axis=5))
    assert result.outcome == "unknown"
    assert result.person_id is None


def test_inactive_person_excluded_from_gallery(enrolled_person):
    enrolled_person.is_active = False
    db.session.commit()
    matcher.invalidate_gallery()

    result = matcher.match_embedding(unit_vector(axis=0))
    assert result.outcome == "unknown"


def test_sample_embeddings_not_matched_only_centroids(app):
    person = Person(code="P002", full_name="Sample Only")
    db.session.add(person)
    sample = FaceEmbedding(person=person, is_centroid=False)
    sample.set_vector(unit_vector(axis=0))
    db.session.add(sample)
    db.session.commit()
    matcher.invalidate_gallery()

    result = matcher.match_embedding(unit_vector(axis=0))
    assert result.outcome == "unknown"
