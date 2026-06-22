"""
Funções de acesso à tabela 'reservas'.
"""

import sqlite3

DB_PATH = "database/intranet.db"


def listar_proximas_reservas(limite: int = 20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT reservas.*, salas.nome AS sala_nome
        FROM reservas
        JOIN salas ON salas.id = reservas.sala_id
        WHERE date(data_reserva) >= date('now')
        ORDER BY data_reserva ASC, hora_inicio ASC
        LIMIT ?
        """,
        (limite,)
    )
    reservas = cursor.fetchall()
    conn.close()
    return reservas


def existe_conflito(sala_id: int, data_reserva: str, hora_inicio: str, hora_fim: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM reservas
        WHERE sala_id = ?
          AND data_reserva = ?
          AND NOT (hora_fim <= ? OR hora_inicio >= ?)
        """,
        (sala_id, data_reserva, hora_inicio, hora_fim)
    )
    conflito = cursor.fetchone()
    conn.close()
    return conflito is not None


def criar_reserva(sala_id, titulo, responsavel, data_reserva, hora_inicio, hora_fim, observacao=""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reservas
            (sala_id, titulo, responsavel, data_reserva, hora_inicio, hora_fim, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sala_id, titulo, responsavel, data_reserva, hora_inicio, hora_fim, observacao)
    )
    conn.commit()
    reserva_id = cursor.lastrowid
    conn.close()
    return reserva_id
