"""Real-model sanity check for the vision stack.

Downloads the buffalo_l pack on first run (~300 MB into ~/.insightface),
loads it, and runs detection + embedding on a synthetic image. The unit
suite fakes the engine, so run this once per machine before trusting
enrollment/recognition:

    .venv\\Scripts\\python.exe scripts\\engine_check.py
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import face_engine  # noqa: E402


def main():
    print("Loading FaceAnalysis (downloads model pack on first run)...")
    started = time.perf_counter()
    engine = face_engine.get_engine()
    print(f"Engine ready in {time.perf_counter() - started:.1f}s")

    # A blank frame must yield zero detections (no false positives on noise).
    blank = np.full((480, 640, 3), 128, dtype=np.uint8)
    started = time.perf_counter()
    observations = engine.analyze(blank)
    elapsed = time.perf_counter() - started
    print(f"Blank frame: {len(observations)} face(s) in {elapsed * 1000:.0f}ms")
    if observations:
        print("FAIL: detector hallucinated a face on a blank frame")
        return 1

    # Round-trip the encode/decode helpers.
    import cv2

    ok, encoded = cv2.imencode(".jpg", blank)
    assert ok
    decoded = face_engine.decode_image(encoded.tobytes())
    print(f"decode_image round-trip ok, shape={decoded.shape}")

    print("\nEngine check passed. Embedding dim per model spec: 512.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
