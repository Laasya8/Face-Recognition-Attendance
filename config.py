"""Application configuration.

The active configuration is chosen by the FLASK_CONFIG environment variable
(``development`` | ``testing`` | ``production``) and resolved through
``config_map`` in the application factory.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

# The factory refuses to start a production app with this key.
_DEV_SECRET_KEY = "insecure-dev-key-do-not-use-in-production"


class Config:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Attendance/enrollment frames arrive as JPEG snapshots; reject anything
    # larger than 5 MB before it reaches a view.
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

    # CSRF tokens stay valid for the whole login session; the default 1-hour
    # expiry breaks long-running attendance kiosk pages.
    WTF_CSRF_TIME_LIMIT = None

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    # Seeded into the ``settings`` table on first ``flask init-db`` run.
    # Runtime-tunable knobs live in the DB, not here; these are first-boot
    # defaults only.
    DEFAULT_SETTINGS = {
        "similarity_threshold_accept": "0.45",
        "similarity_threshold_review": "0.35",
        "enroll_min_images": "5",
        "enroll_max_images": "10",
        "attendance_cooldown_minutes": "0",
        "store_original_images": "false",
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + (INSTANCE_DIR / "attendance.db").as_posix(),
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # private in-memory database
    WTF_CSRF_ENABLED = False  # tests POST without fetching a token first
    SECRET_KEY = "testing-secret-key"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # requires HTTPS via the reverse proxy
    PREFERRED_URL_SCHEME = "https"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + (INSTANCE_DIR / "attendance.db").as_posix(),
    )


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
