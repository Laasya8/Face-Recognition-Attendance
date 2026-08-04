"""Runtime-tunable key/value settings (thresholds, enrollment limits).

Stored in the DB so operators can tune recognition without a redeploy.
Defaults are seeded from ``Config.DEFAULT_SETTINGS`` by ``flask init-db``.
"""

from app.extensions import db
from app.models import utcnow


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @staticmethod
    def get(key, default=None):
        row = db.session.get(Setting, key)
        return row.value if row is not None else default

    @staticmethod
    def get_float(key, default):
        raw = Setting.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    @staticmethod
    def get_int(key, default):
        raw = Setting.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def set(key, value):
        row = db.session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=str(value))
            db.session.add(row)
        else:
            row.value = str(value)

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"
