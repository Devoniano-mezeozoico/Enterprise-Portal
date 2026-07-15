import os
import sqlite3
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def listar_itens():
    conn = _conn()
    itens = conn.execute("SELECT * FROM estoque_ti WHERE excluido_em IS NULL ORDER BY categoria, nome").fetchall()
    conn.close()
    return itens


def criar_item(nome, categoria, quantidade, localizacao="", observacao=""):
    conn = _conn()
    cursor = conn.execute(
        """
        INSERT INTO estoque_ti(nome, categoria, quantidade, localizacao, observacao)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nome.strip(), categoria.strip(), int(quantidade or 0), localizacao.strip(), observacao.strip()),
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


def atualizar_item(item_id, nome, categoria, quantidade, localizacao="", observacao=""):
    conn = _conn()
    conn.execute(
        """
        UPDATE estoque_ti
        SET nome=?, categoria=?, quantidade=?, localizacao=?, observacao=?,
            atualizado_em=CURRENT_TIMESTAMP
        WHERE id=? AND excluido_em IS NULL
        """,
        (nome.strip(), categoria.strip(), int(quantidade or 0), localizacao.strip(), observacao.strip(), item_id),
    )
    conn.commit()
    conn.close()


def excluir_item(item_id):
    conn = _conn()
    conn.execute("UPDATE estoque_ti SET excluido_em=CURRENT_TIMESTAMP WHERE id=? AND excluido_em IS NULL", (item_id,))
    conn.commit()
    conn.close()


def buscar_item(item_id):
    conn = _conn()
    item = conn.execute("SELECT * FROM estoque_ti WHERE id=? AND excluido_em IS NULL", (item_id,)).fetchone()
    conn.close()
    return item
