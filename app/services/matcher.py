"""Gallery matching: one query embedding against every enrolled centroid.

The gallery (person ids + centroid matrix) is cached in process memory and
rebuilt on demand: enrollment and person edits call ``invalidate_gallery``.
Because stored vectors are L2-normalised, cosine similarity is a single
matrix-vector product — comfortably fast for thousands of enrollees.
"""

import threading
from dataclasses import dataclass

import numpy as np

from app.extensions import db
from app.models import FaceEmbedding, Person, Setting
from app.services.face_engine import MODEL_NAME

# Fallbacks when the settings table has not been seeded; keep in sync with
# Config.DEFAULT_SETTINGS.
DEFAULT_ACCEPT = 0.45
DEFAULT_REVIEW = 0.35

_gallery = None  # (person_ids: list[int], matrix: np.ndarray[N, 512])
_gallery_lock = threading.Lock()


@dataclass
class MatchResult:
    outcome: str  # one of RECOGNITION_OUTCOMES
    person_id: int | None
    similarity: float | None


def invalidate_gallery():
    """Drop the cached gallery; next match reloads from the database."""
    global _gallery
    with _gallery_lock:
        _gallery = None


def _load_gallery():
    rows = db.session.execute(
        db.select(FaceEmbedding)
        .join(Person)
        .where(
            FaceEmbedding.is_centroid.is_(True),
            FaceEmbedding.model_name == MODEL_NAME,
            Person.is_active.is_(True),
        )
    ).scalars()

    person_ids = []
    vectors = []
    for row in rows:
        person_ids.append(row.person_id)
        vectors.append(row.get_vector())

    matrix = (
        np.stack(vectors) if vectors else np.empty((0, 512), dtype=np.float32)
    )
    return person_ids, matrix


def _get_gallery():
    global _gallery
    with _gallery_lock:
        if _gallery is None:
            _gallery = _load_gallery()
        return _gallery


def match_embedding(embedding):
    """Match one normalised query embedding against the gallery.

    Outcomes: ``accepted`` (confident match), ``below_threshold`` (best
    candidate lands in the review band), ``unknown`` (nothing close, or the
    gallery is empty).
    """
    person_ids, matrix = _get_gallery()
    if not person_ids:
        return MatchResult(outcome="unknown", person_id=None, similarity=None)

    accept = Setting.get_float("similarity_threshold_accept", DEFAULT_ACCEPT)
    review = Setting.get_float("similarity_threshold_review", DEFAULT_REVIEW)

    query = np.asarray(embedding, dtype=np.float32)
    similarities = matrix @ query
    best_index = int(np.argmax(similarities))
    best_similarity = float(similarities[best_index])

    if best_similarity >= accept:
        outcome = "accepted"
    elif best_similarity >= review:
        outcome = "below_threshold"
    else:
        return MatchResult(
            outcome="unknown", person_id=None, similarity=best_similarity
        )

    return MatchResult(
        outcome=outcome,
        person_id=person_ids[best_index],
        similarity=best_similarity,
    )
