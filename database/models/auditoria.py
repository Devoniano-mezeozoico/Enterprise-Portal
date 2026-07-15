import hashlib
import json
import uuid

from database.connection import connect_db


SENSITIVE_KEYS = {"senha", "senha_hash", "password", "token", "secret", "csrf"}


def _sanitize(value):
    if value is None:
        return None
    if hasattr(value, "keys") and not isinstance(value, dict):
        value = {key: value[key] for key in value.keys()}
    if isinstance(value, dict):
        return {
            str(key): "[PROTEGIDO]" if any(term in str(key).lower() for term in SENSITIVE_KEYS) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json(value):
    if value is None:
        return None
    return json.dumps(_sanitize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def registrar_evento(*, usuario=None, acao, modulo, registro_id=None, unidade=None,
                     endereco_ip=None, user_agent=None, anterior=None, novo=None,
                     detalhes=None, request_id=None, conexao=None):
    """Registra um evento imutável, isoladamente ou na transação informada."""
    request_id = request_id or str(uuid.uuid4())
    anterior_json = _json(anterior)
    novo_json = _json(novo)
    detalhes_json = _json(detalhes)
    conn = conexao or connect_db()
    gerencia_transacao = conexao is None
    try:
        if gerencia_transacao:
            conn.execute("BEGIN IMMEDIATE")
        ultimo = conn.execute(
            "SELECT integridade_hash FROM auditoria_eventos ORDER BY id DESC LIMIT 1"
        ).fetchone()
        hash_anterior = ultimo["integridade_hash"] if ultimo else ""
        payload = _json({
            "request_id": request_id,
            "usuario_id": usuario["id"] if usuario else None,
            "acao": acao,
            "modulo": modulo,
            "registro_id": str(registro_id) if registro_id is not None else None,
            "unidade_id": unidade["id"] if unidade else None,
            "ip": endereco_ip,
            "anterior": anterior_json,
            "novo": novo_json,
            "detalhes": detalhes_json,
            "hash_anterior": hash_anterior,
        })
        integridade_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        cursor = conn.execute(
            """
            INSERT INTO auditoria_eventos(
                request_id, usuario_id, usuario_nome, usuario_email, acao, modulo,
                registro_id, unidade_id, unidade_codigo, endereco_ip, user_agent,
                dados_anteriores, dados_novos, detalhes, hash_anterior, integridade_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                request_id,
                usuario["id"] if usuario else None,
                usuario["nome"] if usuario else None,
                usuario["email"] if usuario else None,
                acao,
                modulo,
                str(registro_id) if registro_id is not None else None,
                unidade["id"] if unidade else None,
                unidade["codigo"] if unidade else None,
                endereco_ip,
                (user_agent or "")[:500],
                anterior_json,
                novo_json,
                detalhes_json,
                hash_anterior or None,
                integridade_hash,
            ),
        )
        if gerencia_transacao:
            conn.commit()
        return cursor.lastrowid
    except Exception:
        if gerencia_transacao:
            conn.rollback()
        raise
    finally:
        if gerencia_transacao:
            conn.close()


def listar_eventos(*, modulo=None, usuario_id=None, unidade_id=None, termo=None, limite=200):
    condicoes = []
    params = []
    if modulo:
        condicoes.append("modulo = ?")
        params.append(modulo)
    if usuario_id:
        condicoes.append("usuario_id = ?")
        params.append(usuario_id)
    if unidade_id:
        condicoes.append("unidade_id = ?")
        params.append(unidade_id)
    if termo:
        condicoes.append("(usuario_nome LIKE ? OR acao LIKE ? OR modulo LIKE ? OR registro_id LIKE ?)")
        params.extend([f"%{termo}%"] * 4)
    where = " WHERE " + " AND ".join(condicoes) if condicoes else ""
    conn = connect_db(readonly=True)
    rows = conn.execute(
        f"SELECT * FROM auditoria_eventos{where} ORDER BY id DESC LIMIT ?",
        (*params, max(1, min(int(limite or 200), 1000))),
    ).fetchall()
    conn.close()
    return rows


def modulos_disponiveis():
    conn = connect_db(readonly=True)
    rows = conn.execute("SELECT DISTINCT modulo FROM auditoria_eventos ORDER BY modulo").fetchall()
    conn.close()
    return [row[0] for row in rows]


def verificar_integridade():
    conn = connect_db(readonly=True)
    rows = conn.execute("SELECT * FROM auditoria_eventos ORDER BY id").fetchall()
    conn.close()
    anterior = ""
    for row in rows:
        payload = _json({
            "request_id": row["request_id"],
            "usuario_id": row["usuario_id"],
            "acao": row["acao"],
            "modulo": row["modulo"],
            "registro_id": row["registro_id"],
            "unidade_id": row["unidade_id"],
            "ip": row["endereco_ip"],
            "anterior": row["dados_anteriores"],
            "novo": row["dados_novos"],
            "detalhes": row["detalhes"],
            "hash_anterior": anterior,
        })
        esperado = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if (row["hash_anterior"] or "") != anterior or row["integridade_hash"] != esperado:
            return False, row["id"]
        anterior = row["integridade_hash"]
    return True, None
