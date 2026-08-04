"""InsightFace wrapper: JPEG bytes in, embeddings out.

The underlying FaceAnalysis model pack (~300 MB, downloaded to ~/.insightface
on first use) takes seconds to load, so a single instance is created lazily
and shared for the process lifetime. ONNX Runtime sessions are thread-safe,
which makes the shared instance safe under waitress's thread pool.

cv2/insightface are imported inside functions: web-only deployments and the
test suite (which substitutes a fake engine) never pay for them.
"""

import base64
import binascii
import threading
from dataclasses import dataclass

import numpy as np

# Must match FaceEmbedding.model_name — vectors from different packs are not
# comparable and the matcher filters on this string.
MODEL_NAME = "buffalo_l"
_DET_SIZE = (640, 640)

_engine = None
_engine_lock = threading.Lock()


class FaceEngineError(RuntimeError):
    """Image could not be decoded or analysed."""


@dataclass
class FaceObservation:
    """One detected face: where it was and what it looks like."""

    embedding: np.ndarray  # 512-d float32, L2-normalised
    bbox: tuple  # (x1, y1, x2, y2) ints, clamped to the image
    det_score: float  # detector confidence in [0, 1]


def decode_image(data):
    """Decode JPEG/PNG bytes or a base64 string (optionally a data: URL).

    Returns a BGR uint8 array; raises FaceEngineError on undecodable input.
    """
    import cv2

    if isinstance(data, str):
        # Strip a "data:image/jpeg;base64," style prefix if present.
        if data.startswith("data:"):
            _, _, data = data.partition(",")
        try:
            data = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FaceEngineError("invalid base64 image data") from exc

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceEngineError("could not decode image bytes")
    return image


def get_engine():
    """Return the process-wide FaceEngine, creating it on first call."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = FaceEngine()
    return _engine


class FaceEngine:
    def __init__(self):
        from insightface.app import FaceAnalysis

        self._analyzer = FaceAnalysis(
            name=MODEL_NAME,
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
        )
        self._analyzer.prepare(ctx_id=-1, det_size=_DET_SIZE)

    def analyze(self, image_bgr):
        """Detect every face in a BGR image.

        Returns FaceObservations sorted largest-first, so callers that expect
        a single subject can take element 0.
        """
        height, width = image_bgr.shape[:2]
        faces = self._analyzer.get(image_bgr)

        observations = []
        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            bbox = (
                max(x1, 0),
                max(y1, 0),
                min(x2, width),
                min(y2, height),
            )
            embedding = np.asarray(face.normed_embedding, dtype=np.float32)
            observations.append(
                FaceObservation(
                    embedding=embedding,
                    bbox=bbox,
                    det_score=float(face.det_score),
                )
            )

        observations.sort(
            key=lambda o: (o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1]),
            reverse=True,
        )
        return observations


def make_thumbnail(image_bgr, bbox, size=112):
    """Crop a face with margin and encode a small JPEG for the person avatar.

    UI convenience only — recognition never reads thumbnails.
    """
    import cv2

    x1, y1, x2, y2 = bbox
    margin_x = int((x2 - x1) * 0.25)
    margin_y = int((y2 - y1) * 0.25)
    height, width = image_bgr.shape[:2]
    crop = image_bgr[
        max(y1 - margin_y, 0) : min(y2 + margin_y, height),
        max(x1 - margin_x, 0) : min(x2 + margin_x, width),
    ]
    if crop.size == 0:
        raise FaceEngineError("face bounding box lies outside the image")

    crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise FaceEngineError("could not encode thumbnail JPEG")
    return encoded.tobytes()
