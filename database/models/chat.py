import os
import sqlite3
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def criar_mensagem(usuario_id, usuario_nome, mensagem):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_mensagens(usuario_id, usuario_nome, mensagem) VALUES (?, ?, ?)",
        (usuario_id, usuario_nome, mensagem.strip()),
    )
    conn.commit()
    mid = cursor.lastrowid
    conn.close()
    return mid


def listar_mensagens(incluir_apagadas=False, limite=200):
    conn = _conn()
    if incluir_apagadas:
        rows = conn.execute("SELECT * FROM chat_mensagens ORDER BY criado_em DESC, id DESC LIMIT ?", (limite,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM chat_mensagens WHERE apagada=0 ORDER BY criado_em DESC, id DESC LIMIT ?", (limite,)).fetchall()
    conn.close()
    return list(reversed(rows))


def buscar_mensagem(mid):
    conn = _conn()
    msg = conn.execute("SELECT * FROM chat_mensagens WHERE id=?", (mid,)).fetchone()
    conn.close()
    return msg


def apagar_mensagem(mid, apagada_por_id, apagada_por_nome):
    conn = _conn()
    conn.execute(
        """
        UPDATE chat_mensagens
        SET apagada=1, apagada_em=CURRENT_TIMESTAMP,
            apagada_por_id=?, apagada_por_nome=?
        WHERE id=?
        """,
        (apagada_por_id, apagada_por_nome, mid),
    )
    conn.commit()
    conn.close()
