"""Application factory.

This module is the composition root: it loads the environment, selects the
configuration, wires every extension, blueprint, error handler and CLI
command onto the app instance, and hands the finished app back. Nothing else
in the codebase ever constructs or imports an app object directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env must be loaded before importing config: config classes read
# os.environ at import time.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from flask import Flask  # noqa: E402

from config import _DEV_SECRET_KEY, config_map  # noqa: E402
from app.extensions import csrf, db, login_manager, migrate, cors  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "development")
    try:
        config_class = config_map[config_name]
    except KeyError:
        valid = ", ".join(sorted(config_map))
        raise RuntimeError(
            f"Unknown FLASK_CONFIG {config_name!r}; expected one of: {valid}"
        )

    app = Flask(__name__)
    app.config.from_object(config_class)

    if config_name == "production" and app.config["SECRET_KEY"] == _DEV_SECRET_KEY:
        raise RuntimeError(
            "Refusing to start in production without a real SECRET_KEY. "
            "Set it in the environment or .env file."
        )

    os.makedirs(app.instance_path, exist_ok=True)
    configure_logging(app)

    # --- extensions (dependency injection via init_app) ---
    db.init_app(app)
    # render_as_batch: SQLite cannot ALTER columns/constraints in place;
    # batch mode has Alembic rebuild the table via a temp copy instead.
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    # Ensure every model is registered with the metadata before create_all
    # or Alembic autogenerate run.
    from app import models  # noqa: F401

    # --- blueprints ---
    from app.blueprints.api import api_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    # --- cross-cutting registration ---
    from app.errors import register_error_handlers
    from app.cli import register_cli

    register_error_handlers(app)
    register_cli(app)
    _register_security_headers(app)

    app.logger.info("Application created (config=%s)", config_name)
    return app


def _register_security_headers(app):
    """Baseline security headers on every response.

    The CSP permits Bootstrap from jsDelivr plus same-origin assets;
    data:/blob: image sources are needed later for webcam frame previews.
    """

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "frame-ancestors 'none'",
        )
        return response
