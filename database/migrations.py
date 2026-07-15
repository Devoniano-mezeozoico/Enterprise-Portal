import sqlite3

from database.connection import connect_db


def _column_names(conn, table):
    return {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_column(conn, table, column, definition):
    if column not in _column_names(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _migration_001_auditoria_unidades_preservacao(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS unidades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            cidade TEXT,
            tipo TEXT NOT NULL CHECK(tipo IN ('sede', 'filial')),
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS usuario_unidades(
            usuario_id INTEGER PRIMARY KEY,
            unidade_id INTEGER,
            associado_por_id INTEGER,
            associado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY(unidade_id) REFERENCES unidades(id),
            FOREIGN KEY(associado_por_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS registro_unidades(
            modulo TEXT NOT NULL,
            registro_id TEXT NOT NULL,
            unidade_id INTEGER,
            escopo TEXT NOT NULL DEFAULT 'nao_definido'
                CHECK(escopo IN ('nao_definido', 'compartilhado', 'unidade')),
            associado_por_id INTEGER,
            associado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(modulo, registro_id),
            FOREIGN KEY(unidade_id) REFERENCES unidades(id),
            FOREIGN KEY(associado_por_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS auditoria_eventos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            usuario_id INTEGER,
            usuario_nome TEXT,
            usuario_email TEXT,
            acao TEXT NOT NULL,
            modulo TEXT NOT NULL,
            registro_id TEXT,
            unidade_id INTEGER,
            unidade_codigo TEXT,
            endereco_ip TEXT,
            user_agent TEXT,
            dados_anteriores TEXT,
            dados_novos TEXT,
            detalhes TEXT,
            hash_anterior TEXT,
            integridade_hash TEXT NOT NULL,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_auditoria_modulo_registro
            ON auditoria_eventos(modulo, registro_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_auditoria_usuario
            ON auditoria_eventos(usuario_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_auditoria_data
            ON auditoria_eventos(criado_em DESC);
        CREATE INDEX IF NOT EXISTS idx_registro_unidades_unidade
            ON registro_unidades(unidade_id, modulo);

        CREATE TRIGGER IF NOT EXISTS auditoria_eventos_bloquear_update
        BEFORE UPDATE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'Registros de auditoria sao imutaveis');
        END;

        CREATE TRIGGER IF NOT EXISTS auditoria_eventos_bloquear_delete
        BEFORE DELETE ON auditoria_eventos
        BEGIN
            SELECT RAISE(ABORT, 'Registros de auditoria nao podem ser excluidos');
        END;

        CREATE TABLE IF NOT EXISTS atendimento_importacoes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arquivo_origem TEXT NOT NULL,
            tipo_origem TEXT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            unidade_id INTEGER,
            registros_anteriores INTEGER NOT NULL DEFAULT 0,
            registros_novos INTEGER NOT NULL DEFAULT 0,
            criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY(unidade_id) REFERENCES unidades(id)
        );

        CREATE TABLE IF NOT EXISTS atendimento_metricas_historico(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            importacao_id INTEGER NOT NULL,
            registro_original_id INTEGER,
            nome TEXT NOT NULL,
            departamento TEXT,
            qtd_atendimentos INTEGER NOT NULL DEFAULT 0,
            tempo_medio_segundos INTEGER NOT NULL DEFAULT 0,
            tempo_medio_formatado TEXT,
            satisfeitos INTEGER NOT NULL DEFAULT 0,
            nao_satisfeitos INTEGER NOT NULL DEFAULT 0,
            total_pesquisa INTEGER NOT NULL DEFAULT 0,
            satisfacao_percentual REAL NOT NULL DEFAULT 0,
            arquivo_origem TEXT,
            tipo_origem TEXT,
            atualizado_em DATETIME,
            arquivado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(importacao_id) REFERENCES atendimento_importacoes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_atendimento_historico_importacao
            ON atendimento_metricas_historico(importacao_id, registro_original_id);

        INSERT OR IGNORE INTO unidades(codigo, nome, cidade, tipo)
        VALUES('SEDE', 'Sede', NULL, 'sede');
        INSERT OR IGNORE INTO unidades(codigo, nome, cidade, tipo)
        VALUES('FILIAL', 'Filial', NULL, 'filial');
        """
    )

    for table in (
        "noticias",
        "pops",
        "eventos_agenda",
        "reservas",
        "salas",
        "chamados_ti",
        "estoque_ti",
        "hub_apps",
        "usuarios",
    ):
        _add_column(conn, table, "excluido_em", "DATETIME")


def _migration_002_remoto(conn):
    # Evolução aditiva: preserva a tabela e todas as chaves estrangeiras.
    # O tipo organizacional legado continua sede/filial; eh_remoto distingue
    # um local virtual de uma unidade física.
    _add_column(conn, "unidades", "eh_remoto", "INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """
        INSERT OR IGNORE INTO unidades(codigo, nome, cidade, tipo, eh_remoto)
        VALUES('REMOTO', 'Remoto', NULL, 'filial', 1)
        """
    )


def _migration_003_unidades_genericas(conn):
    _add_column(conn, "unidades", "eh_remoto", "INTEGER NOT NULL DEFAULT 0")
    for codigo, nome, tipo, eh_remoto in (
        ("SEDE", "Sede", "sede", 0),
        ("FILIAL", "Filial", "filial", 0),
        ("REMOTO", "Remoto", "filial", 1),
    ):
        conn.execute(
            """
            INSERT OR IGNORE INTO unidades(codigo, nome, cidade, tipo, eh_remoto)
            VALUES(?, ?, NULL, ?, ?)
            """,
            (codigo, nome, tipo, eh_remoto),
        )
        conn.execute(
            """
            UPDATE unidades
            SET nome=?, cidade=NULL, tipo=?, eh_remoto=?
            WHERE codigo=?
            """,
            (nome, tipo, eh_remoto, codigo),
        )


MIGRATIONS = (
    (1, "auditoria_unidades_preservacao", _migration_001_auditoria_unidades_preservacao),
    (2, "remoto", _migration_002_remoto),
    (3, "unidades_genericas", _migration_003_unidades_genericas),
)


def aplicar_migracoes(db_path=None):
    conn = connect_db(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(
                versao INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                aplicado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        aplicadas = {row[0] for row in conn.execute("SELECT versao FROM schema_migrations")}
        for versao, nome, migration in MIGRATIONS:
            if versao in aplicadas:
                continue
            conn.execute("BEGIN IMMEDIATE")
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations(versao, nome) VALUES(?, ?)",
                (versao, nome),
            )
            conn.commit()
        return [row[0] for row in conn.execute("SELECT versao FROM schema_migrations ORDER BY versao")]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("Migracoes aplicadas:", aplicar_migracoes())
