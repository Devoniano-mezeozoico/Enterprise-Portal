"""
Cria (ou atualiza) o banco SQLite do Portal Corporativo com as tabelas
necessárias: acessos, salas e reservas.

Uso:
    python database/scripts/criar_banco.py
"""

import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "intranet.db"
)


def criar_banco():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acessos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            hostname TEXT,
            pagina TEXT,
            navegador TEXT,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            capacidade INTEGER DEFAULT 0,
            descricao TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sala_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            data_reserva DATE NOT NULL,
            hora_inicio TIME NOT NULL,
            hora_fim TIME NOT NULL,
            observacao TEXT,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sala_id) REFERENCES salas(id)
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM salas")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO salas (nome, capacidade) VALUES (?, ?)",
            [
                ("Sala Reunião 01", 8),
                ("Sala Reunião 02", 8),
                ("Sala Diretoria", 12),
                ("Sala Treinamento", 30),
            ]
        )

    conn.commit()
    conn.close()
    print(f"Banco de dados pronto em: {DB_PATH}")


if __name__ == "__main__":
    criar_banco()
