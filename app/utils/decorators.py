"""View decorators for role-based authorization."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from app.models.user import ROLE_RANK


def role_required(minimum_role):
    """Require an authenticated user whose role is at least ``minimum_role``.

    Roles are hierarchical (viewer < operator < admin), so an admin passes an
    operator check. Unauthenticated users are redirected to login by
    ``login_required``; authenticated users below rank receive 403.

    Usage::

        @bp.route("/sessions", methods=["POST"])
        @role_required("operator")
        def create_session(): ...
    """
    if minimum_role not in ROLE_RANK:
        raise ValueError(f"unknown role {minimum_role!r}")

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(minimum_role):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
