"""Enrollment: turn a batch of face images into a person's stored template.

Every image must contain exactly one face — enrollment shots are taken one
subject at a time, and silently picking the largest of several faces risks
enrolling a bystander. Per-sample embeddings are kept for threshold
calibration; the averaged centroid is what the matcher loads.

Re-enrolling replaces the previous template wholesale: mixing vectors from
two capture sessions (haircuts, glasses, lighting rigs) degrades the
centroid.
"""

import numpy as np

from app.extensions import db
from app.models import FaceEmbedding, Setting, utcnow
from app.services import face_engine, matcher


class EnrollmentError(ValueError):
    """Enrollment input rejected; ``problems`` lists per-image reasons."""

    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


def enroll_person(person, images):
    """Build and store embeddings for ``person`` from raw/base64 images.

    Stages all changes on the current DB session; the caller commits.
    Returns the number of sample embeddings stored.
    """
    min_images = Setting.get_int("enroll_min_images", 5)
    max_images = Setting.get_int("enroll_max_images", 10)
    if not min_images <= len(images) <= max_images:
        raise EnrollmentError(
            f"expected between {min_images} and {max_images} images, "
            f"got {len(images)}"
        )

    engine = face_engine.get_engine()

    from app.utils.quality import check_blur, check_lighting
    from app.utils.security import encrypt_image
    from app.models.person import PersonSourceImage
    import base64

    embeddings = []
    det_scores = []
    problems = []
    raw_images_bytes = []
    first_face = None  # (image, bbox) for the thumbnail
    for index, image_data in enumerate(images):
        label = f"image {index + 1}"
        try:
            image = face_engine.decode_image(image_data)
        except face_engine.FaceEngineError as exc:
            problems.append(f"{label}: {exc}")
            continue

        observations = engine.analyze(image)
        if len(observations) == 0:
            problems.append(f"{label}: no face detected")
            continue
        if len(observations) > 1:
            problems.append(
                f"{label}: {len(observations)} faces detected, expected exactly one"
            )
            continue

        observation = observations[0]

        # 1. Blur validation
        is_blur_ok, variance = check_blur(image)
        if not is_blur_ok:
            problems.append(f"{label}: too blurry (variance: {variance:.1f} < 80.0)")
            continue

        # 2. Lighting validation
        is_lighting_ok, brightness = check_lighting(image, observation.bbox)
        if not is_lighting_ok:
            problems.append(f"{label}: poor lighting (brightness: {brightness:.1f} must be in [40.0, 220.0])")
            continue

        embeddings.append(observation.embedding)
        det_scores.append(observation.det_score)

        # Extract raw bytes for storage
        raw_bytes = None
        try:
            if isinstance(image_data, str):
                base64_str = image_data
                if base64_str.startswith("data:"):
                    _, _, base64_str = base64_str.partition(",")
                raw_bytes = base64.b64decode(base64_str, validate=True)
            else:
                raw_bytes = image_data
        except Exception:
            pass
        raw_images_bytes.append(raw_bytes)

        if first_face is None:
            first_face = (image, observation.bbox)

    if problems:
        raise EnrollmentError(
            f"{len(problems)} image(s) unusable; fix and retry", problems
        )

    # Check for duplicate enrollment (if another active person has the same face)
    mean_embedding = np.mean(embeddings, axis=0)
    arr = np.asarray(mean_embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm > 0.0 and np.isfinite(norm):
        normalized_vector = arr / norm
        match_res = matcher.match_embedding(normalized_vector)
        if match_res.outcome == "accepted" and match_res.person_id != person.id:
            from app.models import Person as PersonModel
            conflicting_person = db.session.get(PersonModel, match_res.person_id)
            if conflicting_person:
                raise EnrollmentError(
                    f"Face already enrolled under: {conflicting_person.full_name} ({conflicting_person.code})"
                )

    # Replace any previous template in the same transaction.
    person.embeddings.clear()
    person.source_images.clear()

    for embedding, det_score in zip(embeddings, det_scores):
        sample = FaceEmbedding(
            person=person,
            is_centroid=False,
            quality_score=det_score,
            model_name=face_engine.MODEL_NAME,
        )
        sample.set_vector(embedding)
        db.session.add(sample)

    # Optionally store encrypted original images
    if Setting.get("store_original_images", "false").lower() == "true":
        for raw_bytes in raw_images_bytes:
            if raw_bytes:
                encrypted = encrypt_image(raw_bytes)
                source_img = PersonSourceImage(person=person, encrypted_data=encrypted)
                db.session.add(source_img)

    centroid = FaceEmbedding(
        person=person,
        is_centroid=True,
        quality_score=float(np.mean(det_scores)),
        model_name=face_engine.MODEL_NAME,
    )
    # set_vector re-normalises, turning the mean into the true centroid
    # direction on the unit sphere.
    centroid.set_vector(np.mean(embeddings, axis=0))
    db.session.add(centroid)

    person.thumbnail = face_engine.make_thumbnail(*first_face)
    person.enrolled_at = utcnow()

    matcher.invalidate_gallery()
    return len(embeddings)
