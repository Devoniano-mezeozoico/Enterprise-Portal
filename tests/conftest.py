import importlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def portal_app(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    shutil.copytree(PROJECT_ROOT / "database", runtime / "database")
    (runtime / "logs").mkdir(exist_ok=True)
    (runtime / "static" / "uploads" / "noticias").mkdir(parents=True, exist_ok=True)
    (runtime / "static" / "uploads" / "pops").mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(runtime)
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "pytest-secret-key")
    monkeypatch.setenv("DATABASE_PATH", str(runtime / "database" / "intranet.db"))
    monkeypatch.setenv("LOG_DIR", str(runtime / "logs"))
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "1")

    sys.path.insert(0, str(PROJECT_ROOT))
    for name in list(sys.modules):
        if (
            name == "app"
            or name in {"config", "security", "database.connection", "database.migrations"}
            or name.startswith("database.models.")
        ):
            sys.modules.pop(name, None)
    portal = importlib.import_module("app")
    portal.app.config.update(TESTING=True)
    return portal


@pytest.fixture()
def client(portal_app):
    return portal_app.app.test_client()


def db_path(portal_app):
    return Path(portal_app.app.config["DB_PATH"])


def fetch_user_id(portal_app, where_sql, params=()):
    conn = sqlite3.connect(db_path(portal_app))
    row = conn.execute(
        f"SELECT id FROM usuarios WHERE {where_sql} LIMIT 1",
        params,
    ).fetchone()
    conn.close()
    return row[0] if row else None


def login_as(client, user_id):
    with client.session_transaction() as sess:
        sess.clear()
        sess["usuario_id"] = user_id


def csrf_token(client):
    with client.session_transaction() as sess:
        token = sess.get("_csrf_token")
        if not token:
            token = "pytest-csrf-token"
            sess["_csrf_token"] = token
        return token


def post_form(client, path, data=None, **kwargs):
    payload = dict(data or {})
    payload.setdefault("_csrf_token", csrf_token(client))
    return client.post(path, data=payload, **kwargs)
