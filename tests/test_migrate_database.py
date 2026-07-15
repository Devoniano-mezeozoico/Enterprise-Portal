import importlib.util
import sqlite3
from pathlib import Path


def _carregar_script():
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "migrate_database.py"
    spec = importlib.util.spec_from_file_location("migrate_database_test", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_migrator_allows_additions_and_preserves_every_previous_row(tmp_path):
    banco = tmp_path / "migration.db"
    conn = sqlite3.connect(banco)
    conn.executescript(
        """
        CREATE TABLE schema_migrations(
            versao INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            aplicado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO schema_migrations(versao,nome)
        VALUES(1,'auditoria_unidades_preservacao');

        CREATE TABLE unidades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            cidade TEXT,
            tipo TEXT NOT NULL CHECK(tipo IN ('sede', 'filial')),
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO unidades(codigo,nome,tipo) VALUES('SEDE','Sede','sede');

        CREATE TABLE legado(id INTEGER PRIMARY KEY, valor TEXT NOT NULL);
        INSERT INTO legado(id,valor) VALUES(1,'intacto'),(2,'também intacto');
        """
    )
    legado_antes = conn.execute("SELECT * FROM legado ORDER BY id").fetchall()
    conn.commit()
    conn.close()

    script = _carregar_script()
    backup, versoes, preservadas = script.migrate_with_backup(banco)

    assert backup.is_file()
    assert versoes == [1, 2, 3]
    assert preservadas == 3
    conn = sqlite3.connect(banco)
    assert conn.execute("SELECT * FROM legado ORDER BY id").fetchall() == legado_antes
    assert conn.execute(
        "SELECT nome,eh_remoto FROM unidades WHERE codigo='REMOTO'"
    ).fetchone() == ("Remoto", 1)
    conn.close()
