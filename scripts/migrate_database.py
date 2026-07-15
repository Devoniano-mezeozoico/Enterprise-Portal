"""Aplica migrações aditivas com backup e verificação dos dados existentes."""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from database.connection import database_path
from database.migrations import aplicar_migracoes


def _tables(conn):
    return [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def _columns(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _snapshot(conn, table, columns):
    quoted = ",".join(f'"{column}"' for column in columns)
    order = '"id"' if "id" in columns else quoted
    rows = Counter()
    for row in conn.execute(f'SELECT {quoted} FROM "{table}" ORDER BY {order}'):
        payload = json.dumps(list(row), ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        rows[hashlib.sha256(payload).hexdigest()] += 1
    return rows


def migrate_with_backup(path=None):
    source_path = database_path(path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Banco não encontrado: {source_path}")

    source = sqlite3.connect(str(source_path), timeout=30)
    source.execute("PRAGMA busy_timeout=30000")
    tables = _tables(source)
    columns = {table: _columns(source, table) for table in tables}
    before = {table: _snapshot(source, table, columns[table]) for table in tables}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = source_path.with_name(f"{source_path.stem}.before_migration_{stamp}{source_path.suffix}")
    backup = sqlite3.connect(str(backup_path))
    source.backup(backup)
    backup.close()
    verifier = sqlite3.connect(str(backup_path))
    backup_ok = verifier.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    verifier.close()
    if not backup_ok:
        source.close()
        raise RuntimeError("A cópia de segurança não passou na verificação de integridade.")
    source.close()

    versions = aplicar_migracoes(source_path)

    migrated = sqlite3.connect(str(source_path))
    after = {table: _snapshot(migrated, table, columns[table]) for table in tables}
    migrated.close()
    changed = [table for table in tables if before[table] - after[table]]
    if changed:
        raise RuntimeError("Linhas anteriores divergiram após a migração: " + ", ".join(changed))
    return backup_path, versions, len(tables)


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    backup, versions, preserved = migrate_with_backup()
    print(f"Backup verificado: {backup}")
    print(f"Migrações aplicadas: {versions}")
    print(f"Tabelas anteriores preservadas: {preserved}")
