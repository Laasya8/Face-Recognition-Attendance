"""Symmetric encryption utilities for original student snapshots."""

import base64
import hashlib
from cryptography.fernet import Fernet
from flask import current_app


def _get_fernet():
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key:
        raise ValueError("SECRET_KEY must be configured in Flask app.")
    # Fernet requires a 32-byte url-safe base64 key
    key_bytes = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_image(raw_bytes: bytes) -> bytes:
    """Encrypt raw image bytes using a secure Fernet key derived from SECRET_KEY."""
    f = _get_fernet()
    return f.encrypt(raw_bytes)


def decrypt_image(encrypted_bytes: bytes) -> bytes:
    """Decrypt image bytes back to raw format using the derived Fernet key."""
    f = _get_fernet()
    return f.decrypt(encrypted_bytes)
