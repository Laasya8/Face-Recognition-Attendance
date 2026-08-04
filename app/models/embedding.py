"""Face embedding storage.

Each row is one 512-dimensional float32 vector (2 KB) produced by the
InsightFace ArcFace model. Vectors are L2-normalised before storage so that
cosine similarity downstream reduces to a dot product.
"""

import numpy as np
from sqlalchemy.orm import validates

from app.extensions import db
from app.models import utcnow

EMBEDDING_DIM = 512
EMBEDDING_BYTES = EMBEDDING_DIM * 4  # float32


class FaceEmbedding(db.Model):
    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(
        db.Integer,
        db.ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Raw little-endian float32 bytes; use set_vector/get_vector, never assign
    # this column directly.
    vector = db.Column(db.LargeBinary(EMBEDDING_BYTES), nullable=False)
    # True for the averaged template built from all enrollment images.
    is_centroid = db.Column(db.Boolean, nullable=False, default=False)
    quality_score = db.Column(db.Float)
    # Embeddings from different model packs are not comparable; the matcher
    # only loads vectors whose model matches the active one.
    model_name = db.Column(db.String(32), nullable=False, default="buffalo_l")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    person = db.relationship("Person", back_populates="embeddings")

    @validates("quality_score")
    def _validate_quality_score(self, _key, value):
        # Detector confidence scale; guards against storing a similarity or
        # a percentage here by mistake.
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError(f"quality_score must be within [0, 1], got {value}")
        return value

    def set_vector(self, array):
        """Validate, L2-normalise and serialise a 512-d vector."""
        arr = np.asarray(array, dtype=np.float32).reshape(-1)
        if arr.shape != (EMBEDDING_DIM,):
            raise ValueError(
                f"expected a {EMBEDDING_DIM}-d vector, got shape {arr.shape}"
            )
        norm = float(np.linalg.norm(arr))
        if norm == 0.0 or not np.isfinite(norm):
            raise ValueError("embedding vector has zero or non-finite norm")
        self.vector = (arr / norm).tobytes()

    def get_vector(self):
        """Deserialise back to a float32 NumPy array (read-only view)."""
        return np.frombuffer(self.vector, dtype=np.float32)

    def __repr__(self):
        kind = "centroid" if self.is_centroid else "sample"
        return f"<FaceEmbedding person={self.person_id} {kind}>"
