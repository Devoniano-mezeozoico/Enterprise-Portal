import os
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def database_path(path=None):
    configured = path or os.environ.get("DATABASE_PATH") or "database/intranet.db"
    resolved = Path(configured).expanduser()
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved


class DynamicDatabasePath(os.PathLike):
    """Resolve DATABASE_PATH a cada conexão, inclusive em testes isolados."""

    def __fspath__(self):
        return str(database_path())

    def __str__(self):
        return self.__fspath__()


DYNAMIC_DATABASE_PATH = DynamicDatabasePath()


def connect_db(path=None, *, readonly=False):
    db_path = database_path(path)
    if readonly:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    if readonly:
        conn.execute("PRAGMA query_only=ON")
    return conn
