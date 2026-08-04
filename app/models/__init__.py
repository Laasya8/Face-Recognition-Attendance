"""ORM models package.

Importing this package registers every model with SQLAlchemy's metadata,
which ``db.create_all`` and Alembic autogenerate both rely on.
"""

from datetime import datetime, timezone


def utcnow():
    """Naive UTC timestamp.

    SQLite has no timezone-aware column type, so the whole schema stores
    naive UTC and converts at the presentation layer.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


from app.models.user import AdminUser  # noqa: E402
from app.models.person import Person, PersonSourceImage  # noqa: E402
from app.models.embedding import FaceEmbedding  # noqa: E402
from app.models.session import AttendanceSession  # noqa: E402
from app.models.attendance import AttendanceRecord  # noqa: E402
from app.models.audit import AuditLog, RecognitionLog  # noqa: E402
from app.models.setting import Setting  # noqa: E402

__all__ = [
    "AdminUser",
    "Person",
    "PersonSourceImage",
    "FaceEmbedding",
    "AttendanceSession",
    "AttendanceRecord",
    "AuditLog",
    "RecognitionLog",
    "Setting",
    "utcnow",
]
