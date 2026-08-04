"""Flask extension singletons.

Extensions are instantiated here without an app and bound in the application
factory via ``init_app``. Modules import these singletons instead of an app
instance, which keeps imports one-directional and lets tests build their own
isolated app against the same objects.
"""

import sqlite3

from flask import flash, jsonify, redirect, request, url_for
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
cors = CORS()

# Anonymous visitors hitting a protected page are sent to the login form.
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to access this page."
login_manager.login_message_category = "warning"


@login_manager.unauthorized_handler
def _unauthorized():
    """API callers get a JSON 401; browser visitors get the login redirect."""
    if request.path.startswith("/api/"):
        return (
            jsonify(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": "Authentication required.",
                    }
                }
            ),
            401,
        )
    flash(login_manager.login_message, login_manager.login_message_category)
    return redirect(url_for(login_manager.login_view, next=request.url))


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """Apply per-connection SQLite pragmas.

    WAL lets many readers proceed while attendance writes happen, and SQLite
    ships with foreign-key enforcement OFF — without this pragma the
    ON DELETE CASCADE on face_embeddings would silently not fire.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
