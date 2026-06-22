"""
Utilitário de linha de comando para inspecionar o banco intranet.db
sem precisar abrir um cliente SQLite externo.

Uso:
    python database/scripts/console_db.py acessos
    python database/scripts/console_db.py salas
    python database/scripts/console_db.py reservas
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "intranet.db"
)

TABELAS_VALIDAS = {"acessos", "salas", "reservas"}


def listar(tabela: str, limite: int = 50):
    if tabela not in TABELAS_VALIDAS:
        print(f"Tabela inválida. Use uma de: {', '.join(sorted(TABELAS_VALIDAS))}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {tabela} ORDER BY id DESC LIMIT ?", (limite,))
    linhas = cursor.fetchall()
    conn.close()

    if not linhas:
        print(f"Nenhum registro encontrado em '{tabela}'.")
        return

    colunas = linhas[0].keys()
    print(" | ".join(colunas))
    print("-" * 80)
    for linha in linhas:
        print(" | ".join(str(linha[col]) for col in colunas))


if __name__ == "__main__":
    tabela = sys.argv[1] if len(sys.argv) > 1 else "acessos"
    listar(tabela)
