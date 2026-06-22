import sqlite3
from datetime import datetime

DB_PATH = "database/intranet.db"
RESPONSAVEIS_TI = ("Matheus", "Bruno", "Gabriel")
STATUS_CHAMADO = ("aberto", "em_atendimento", "resolvido")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def criar_chamado(usuario_id, usuario_nome, titulo, descricao, prioridade="normal"):
    conn = _conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO chamados_ti
        (usuario_id, usuario_nome, titulo, descricao, prioridade, status)
        VALUES (?, ?, ?, ?, ?, 'aberto')
        """,
        (usuario_id, usuario_nome, titulo.strip(), descricao.strip(), prioridade),
    )
    conn.commit()
    chamado_id = cursor.lastrowid
    conn.close()
    return chamado_id


def listar_chamados(usuario_id=None, admin=False):
    conn = _conn()
    cursor = conn.cursor()
    if admin:
        cursor.execute("SELECT * FROM chamados_ti ORDER BY criado_em DESC")
    else:
        cursor.execute(
            "SELECT * FROM chamados_ti WHERE usuario_id=? ORDER BY criado_em DESC",
            (usuario_id,),
        )
    chamados = cursor.fetchall()
    conn.close()
    return chamados


def buscar_chamado(chamado_id):
    conn = _conn()
    chamado = conn.execute("SELECT * FROM chamados_ti WHERE id=?", (chamado_id,)).fetchone()
    conn.close()
    return chamado


def atualizar_atendimento(chamado_id, responsavel, resposta, status):
    if responsavel not in RESPONSAVEIS_TI:
        raise ValueError("Responsavel invalido.")
    if status not in STATUS_CHAMADO:
        raise ValueError("Status invalido.")

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chamado = buscar_chamado(chamado_id)
    if not chamado:
        return False

    primeira_resposta = chamado["respondido_em"] or agora
    resolvido_em = chamado["resolvido_em"]
    if status == "resolvido" and not resolvido_em:
        resolvido_em = agora
    if status != "resolvido":
        resolvido_em = None

    conn = _conn()
    conn.execute(
        """
        UPDATE chamados_ti
        SET responsavel=?, resposta=?, status=?, respondido_em=?, resolvido_em=?,
            atualizado_em=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (responsavel, resposta.strip(), status, primeira_resposta, resolvido_em, chamado_id),
    )
    conn.commit()
    conn.close()
    return True


def excluir_chamado(chamado_id):
    conn = _conn()
    conn.execute("DELETE FROM chamados_ti WHERE id=?", (chamado_id,))
    conn.commit()
    conn.close()


def _duracao(inicio, fim):
    if not inicio or not fim:
        return None
    try:
        dt_inicio = datetime.strptime(inicio, "%Y-%m-%d %H:%M:%S")
        dt_fim = datetime.strptime(fim, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    minutos = int((dt_fim - dt_inicio).total_seconds() // 60)
    if minutos < 60:
        return f"{minutos} min"
    horas, mins = divmod(minutos, 60)
    if horas < 24:
        return f"{horas}h {mins}min"
    dias, horas = divmod(horas, 24)
    return f"{dias}d {horas}h"


def tempo_resposta(chamado):
    return _duracao(chamado["criado_em"], chamado["respondido_em"])


def tempo_resolucao(chamado):
    return _duracao(chamado["criado_em"], chamado["resolvido_em"])
