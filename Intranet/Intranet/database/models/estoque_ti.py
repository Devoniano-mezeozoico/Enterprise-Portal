import sqlite3

DB_PATH = "database/intranet.db"


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def listar_itens():
    conn = _conn()
    itens = conn.execute("SELECT * FROM estoque_ti ORDER BY categoria, nome").fetchall()
    conn.close()
    return itens


def criar_item(nome, categoria, quantidade, localizacao="", observacao=""):
    conn = _conn()
    conn.execute(
        """
        INSERT INTO estoque_ti(nome, categoria, quantidade, localizacao, observacao)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nome.strip(), categoria.strip(), int(quantidade or 0), localizacao.strip(), observacao.strip()),
    )
    conn.commit()
    conn.close()


def atualizar_item(item_id, nome, categoria, quantidade, localizacao="", observacao=""):
    conn = _conn()
    conn.execute(
        """
        UPDATE estoque_ti
        SET nome=?, categoria=?, quantidade=?, localizacao=?, observacao=?,
            atualizado_em=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (nome.strip(), categoria.strip(), int(quantidade or 0), localizacao.strip(), observacao.strip(), item_id),
    )
    conn.commit()
    conn.close()


def excluir_item(item_id):
    conn = _conn()
    conn.execute("DELETE FROM estoque_ti WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
