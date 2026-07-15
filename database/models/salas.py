"""
Funções de acesso à tabela 'salas'.
"""

import os
import sqlite3
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH


def listar_salas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salas WHERE excluido_em IS NULL ORDER BY nome")
    salas = cursor.fetchall()
    conn.close()
    return salas


def buscar_sala_por_nome(nome: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salas WHERE nome = ? AND excluido_em IS NULL", (nome,))
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


def buscar_sala_por_id(sala_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM salas WHERE id = ? AND excluido_em IS NULL", (sala_id,))
    sala = cursor.fetchone()
    conn.close()
    return sala


def atualizar_sala(sala_id: int, nome: str, capacidade: int = 0, descricao: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE salas SET nome = ?, capacidade = ?, descricao = ? WHERE id = ? AND excluido_em IS NULL",
        (nome, capacidade, descricao, sala_id)
    )
    conn.commit()
    conn.close()


def sala_tem_reservas(sala_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM reservas WHERE sala_id = ? LIMIT 1", (sala_id,))
    existe = cursor.fetchone() is not None
    conn.close()
    return existe


def excluir_sala(sala_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE salas SET excluido_em=CURRENT_TIMESTAMP WHERE id = ? AND excluido_em IS NULL", (sala_id,))
    conn.commit()
    conn.close()
