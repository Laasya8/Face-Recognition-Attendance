"""Login accounts for the web application (not enrollees)."""

from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import utcnow

ROLES = ("viewer", "operator", "admin")

# Higher rank implies every capability of the ranks below it.
ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="viewer")
    # Shadows UserMixin.is_active on purpose: Flask-Login treats a falsy value
    # as a disabled account and blocks login.
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.CheckConstraint(role.in_(ROLES), name="ck_admin_users_role"),
    )

    @validates("username")
    def _validate_username(self, _key, value):
        # Normalised here so lookups can rely on lowercase-in-DB regardless
        # of which code path created the account.
        if value is None or len(value.strip()) < 3:
            raise ValueError("username must be at least 3 characters")
        return value.strip().lower()

    @validates("role")
    def _validate_role(self, _key, value):
        # The DB CheckConstraint is the backstop; failing here gives the
        # caller a clear error before flush instead of an IntegrityError.
        if value not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, got {value!r}")
        return value

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, minimum_role):
        """True when this user's role is at least ``minimum_role``."""
        return ROLE_RANK.get(self.role, 0) >= ROLE_RANK[minimum_role]

    def __repr__(self):
        return f"<AdminUser {self.username} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))
