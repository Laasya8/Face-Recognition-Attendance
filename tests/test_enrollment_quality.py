"""Tests for image quality validation and secure storage in enrollment."""

import pytest
import numpy as np
from app.extensions import db
from app.models import Person, PersonSourceImage, Setting
from app.services.enrollment import enroll_person, EnrollmentError
from app.utils.quality import check_blur, check_lighting
from app.utils.security import encrypt_image, decrypt_image
from tests.conftest import observation


def test_encryption_roundtrip(app):
    # Test encryption and decryption of raw bytes
    original = b"fake-jpeg-bytes-here-12345"
    encrypted = encrypt_image(original)
    assert encrypted != original
    decrypted = decrypt_image(encrypted)
    assert decrypted == original


def test_quality_check_blur():
    # 1. Textured/noisy image should pass
    good_img = np.random.randint(100, 150, (240, 320, 3), dtype=np.uint8)
    ok, var = check_blur(good_img)
    assert ok
    assert var >= 80.0

    # 2. Solid/flat image should fail (blurry)
    blurry_img = np.zeros((240, 320, 3), dtype=np.uint8)
    ok, var = check_blur(blurry_img)
    assert not ok
    assert var < 80.0


def test_quality_check_lighting():
    bbox = (0, 0, 100, 100)

    # 1. Normal lighting
    good_img = np.full((100, 100, 3), 120, dtype=np.uint8)
    ok, val = check_lighting(good_img, bbox)
    assert ok
    assert 40.0 <= val <= 220.0

    # 2. Too dark
    dark_img = np.full((100, 100, 3), 10, dtype=np.uint8)
    ok, val = check_lighting(dark_img, bbox)
    assert not ok
    assert val < 40.0

    # 3. Too bright
    bright_img = np.full((100, 100, 3), 240, dtype=np.uint8)
    ok, val = check_lighting(bright_img, bbox)
    assert not ok
    assert val > 220.0


def test_enrollment_quality_validations(app, fake_vision, monkeypatch):
    # Set up person
    p = Person(code="P99", full_name="Quality Test")
    db.session.add(p)
    db.session.commit()

    # Define standard valid face observations
    obs = [observation(np.ones(512, dtype=np.float32))]
    fake_vision([obs, obs, obs, obs, obs]) # 5 images

    # 1. Enrolling standard valid (noisy) images should pass
    images = ["data:image/jpeg;base64,AAAA"] * 5
    count = enroll_person(p, images)
    assert count == 5
    db.session.commit()

    # 2. Test blur failure
    monkeypatch.setattr("app.utils.quality.check_blur", lambda img, threshold=80.0: (False, 10.0))
    fake_vision([obs, obs, obs, obs, obs])
    with pytest.raises(EnrollmentError) as exc_info:
        enroll_person(p, images)
    assert any("too blurry" in prob for prob in exc_info.value.problems)
        
    # Restore check_blur and test lighting failure
    monkeypatch.undo()
    monkeypatch.setattr("app.utils.quality.check_lighting", lambda img, bbox: (False, 250.0))
    fake_vision([obs, obs, obs, obs, obs])
    with pytest.raises(EnrollmentError) as exc_info:
        enroll_person(p, images)
    assert any("poor lighting" in prob for prob in exc_info.value.problems)


def test_enrollment_encrypted_storage(app, fake_vision, monkeypatch):
    # Set up person
    p = Person(code="P100", full_name="Encryption Storage Test")
    db.session.add(p)
    db.session.commit()

    obs = [observation(np.ones(512, dtype=np.float32))]
    
    # Enable store_original_images in settings table
    Setting.set("store_original_images", "true")
    db.session.commit()

    fake_vision([obs, obs, obs, obs, obs])
    images = ["data:image/jpeg;base64,YWJjZGU="] * 5 # base64 for "abcde"
    
    count = enroll_person(p, images)
    assert count == 5
    db.session.commit()

    # Verify encrypted images are stored
    stored = PersonSourceImage.query.filter_by(person_id=p.id).all()
    assert len(stored) == 5
    
    # Decrypt and verify they match the original image bytes ("abcde")
    for img in stored:
        dec = decrypt_image(img.encrypted_data)
        assert dec == b"abcde"

    # Disable storage and verify old ones are deleted, new ones not created
    Setting.set("store_original_images", "false")
    db.session.commit()

    fake_vision([obs, obs, obs, obs, obs])
    count2 = enroll_person(p, images)
    assert count2 == 5
    db.session.commit()

    # The relationship cascade delete-orphan will clear the old ones
    stored = PersonSourceImage.query.filter_by(person_id=p.id).all()
    assert len(stored) == 0
