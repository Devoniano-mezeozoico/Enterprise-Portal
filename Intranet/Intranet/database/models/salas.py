"""
Funções de acesso à tabela 'salas'.
"""

import sqlite3

DB_PATH = "database/intranet.db"


def listar_salas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salas ORDER BY nome")
    salas = cursor.fetchall()
    conn.close()
    return salas


def buscar_sala_por_nome(nome: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salas WHERE nome = ?", (nome,))
    sala = cursor.fetchone()
    conn.close()
    return sala


def criar_sala(nome: str, capacidade: int = 0, descricao: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO salas (nome, capacidade, descricao) VALUES (?, ?, ?)",
        (nome, capacidade, descricao)
    )
    conn.commit()
    sala_id = cursor.lastrowid
    conn.close()
    return sala_id
