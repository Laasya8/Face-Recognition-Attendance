from flask import Blueprint

# Mounted at /api/v1 by the application factory.
api_bp = Blueprint("api", __name__)

from app.blueprints.api import routes  # noqa: E402,F401
