from database.connection import connect_db


def _selecao_unidades():
    return "*, CASE WHEN eh_remoto = 1 THEN 'remoto' ELSE tipo END AS tipo_exibicao"


def _normalizar_tipo(tipo):
    tipo = (tipo or "").strip().lower()
    if tipo == "remoto":
        return "filial", 1
    if tipo not in {"sede", "filial"}:
        raise ValueError("Tipo de local inválido.")
    return tipo, 0


def listar_unidades(apenas_ativas=False):
    conn = connect_db()
    sql = f"SELECT {_selecao_unidades()} FROM unidades"
    if apenas_ativas:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY CASE WHEN eh_remoto=1 THEN 2 WHEN tipo='sede' THEN 0 ELSE 1 END, nome"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def buscar_unidade(unidade_id):
    if not unidade_id:
        return None
    conn = connect_db()
    row = conn.execute(
        f"SELECT {_selecao_unidades()} FROM unidades WHERE id = ?", (unidade_id,)
    ).fetchone()
    conn.close()
    return row


def criar_unidade(codigo, nome, cidade, tipo):
    tipo_banco, eh_remoto = _normalizar_tipo(tipo)
    conn = connect_db()
    cursor = conn.execute(
        "INSERT INTO unidades(codigo, nome, cidade, tipo, eh_remoto) VALUES(?,?,?,?,?)",
        (codigo.strip().upper(), nome.strip(), cidade.strip() or None, tipo_banco, eh_remoto),
    )
    conn.commit()
    unidade_id = cursor.lastrowid
    conn.close()
    return unidade_id


def atualizar_unidade(unidade_id, codigo, nome, cidade, tipo, ativo):
    tipo_banco, eh_remoto = _normalizar_tipo(tipo)
    conn = connect_db()
    conn.execute(
        """
        UPDATE unidades
        SET codigo=?, nome=?, cidade=?, tipo=?, eh_remoto=?, ativo=?, atualizado_em=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (
            codigo.strip().upper(), nome.strip(), cidade.strip() or None,
            tipo_banco, eh_remoto, 1 if ativo else 0, unidade_id,
        ),
    )
    conn.commit()
    conn.close()


def unidade_do_usuario(usuario_id):
    if not usuario_id:
        return None
    conn = connect_db()
    row = conn.execute(
        """
        SELECT u.*, CASE WHEN u.eh_remoto = 1 THEN 'remoto' ELSE u.tipo END AS tipo_exibicao
        FROM usuario_unidades uu
        INNER JOIN unidades u ON u.id = uu.unidade_id
        WHERE uu.usuario_id = ?
        """,
        (usuario_id,),
    ).fetchone()
    conn.close()
    return row


def vincular_usuario(usuario_id, unidade_id, associado_por_id=None):
    conn = connect_db()
    if not unidade_id:
        conn.execute("DELETE FROM usuario_unidades WHERE usuario_id=?", (usuario_id,))
        conn.commit()
        conn.close()
        return
    conn.execute(
        """
        INSERT INTO usuario_unidades(usuario_id, unidade_id, associado_por_id, associado_em)
        VALUES(?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(usuario_id) DO UPDATE SET
            unidade_id=excluded.unidade_id,
            associado_por_id=excluded.associado_por_id,
            associado_em=CURRENT_TIMESTAMP
        """,
        (usuario_id, unidade_id, associado_por_id),
    )
    conn.commit()
    conn.close()


def unidades_por_usuario():
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT uu.usuario_id, u.id, u.codigo, u.nome,
               CASE WHEN u.eh_remoto = 1 THEN 'remoto' ELSE u.tipo END AS tipo_exibicao
        FROM usuario_unidades uu
        INNER JOIN unidades u ON u.id = uu.unidade_id
        """
    ).fetchall()
    conn.close()
    return {row["usuario_id"]: row for row in rows}


def vincular_registro(modulo, registro_id, unidade_id=None, escopo="nao_definido", associado_por_id=None):
    if escopo not in {"nao_definido", "compartilhado", "unidade"}:
        raise ValueError("Escopo de unidade invalido.")
    if escopo == "unidade" and not unidade_id:
        raise ValueError("Selecione uma unidade para o escopo por unidade.")
    conn = connect_db()
    conn.execute(
        """
        INSERT INTO registro_unidades(modulo, registro_id, unidade_id, escopo, associado_por_id, associado_em)
        VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(modulo, registro_id) DO UPDATE SET
            unidade_id=excluded.unidade_id,
            escopo=excluded.escopo,
            associado_por_id=excluded.associado_por_id,
            associado_em=CURRENT_TIMESTAMP
        """,
        (modulo, str(registro_id), unidade_id or None, escopo, associado_por_id),
    )
    conn.commit()
    conn.close()


def unidade_do_registro(modulo, registro_id):
    conn = connect_db()
    row = conn.execute(
        """
        SELECT ru.*, u.codigo, u.nome AS unidade_nome
        FROM registro_unidades ru
        LEFT JOIN unidades u ON u.id = ru.unidade_id
        WHERE ru.modulo=? AND ru.registro_id=?
        """,
        (modulo, str(registro_id)),
    ).fetchone()
    conn.close()
    return row


def unidades_por_registro(modulo):
    conn = connect_db()
    rows = conn.execute(
        """
        SELECT ru.*, u.codigo, u.nome AS unidade_nome
        FROM registro_unidades ru
        LEFT JOIN unidades u ON u.id = ru.unidade_id
        WHERE ru.modulo=?
        """,
        (modulo,),
    ).fetchall()
    conn.close()
    return {str(row["registro_id"]): row for row in rows}


def resumo_vinculos():
    conn = connect_db(readonly=True)
    rows = conn.execute(
        """
        SELECT u.id,
               (SELECT COUNT(*) FROM usuario_unidades uu WHERE uu.unidade_id=u.id) AS usuarios,
               (SELECT COUNT(*) FROM registro_unidades ru WHERE ru.unidade_id=u.id) AS registros
        FROM unidades u
        """
    ).fetchall()
    conn.close()
    return {row["id"]: row for row in rows}
