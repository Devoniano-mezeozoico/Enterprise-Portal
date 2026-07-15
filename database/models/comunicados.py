import os
import sqlite3
import unicodedata
from datetime import datetime
from database.connection import DYNAMIC_DATABASE_PATH


DB_PATH = DYNAMIC_DATABASE_PATH

ABAS_PADRAO = (
    ("noticias", "Notícias", "noticias", "fa-solid fa-newspaper", 10),
    ("apps", "Hub de Apps", "hub_apps", "fa-solid fa-mobile-screen", 20),
    ("agenda", "Agenda/Reservas", "agenda", "fa-solid fa-calendar-days", 30),
    ("chat", "Chat", "chat", "fa-solid fa-comments", 40),
    ("pops", "POPs", "pops", "fa-solid fa-book", 50),
    ("chamados_ti", "Chamados TI", "chamados_ti", "fa-solid fa-headset", 60),
    ("ia", "IA Corporativa", "ia", "fa-solid fa-robot", 70),
)


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalizar(texto):
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in valor if not unicodedata.combining(c)).strip().lower()


def usuario_eh_gestor(usuario):
    if not usuario or not usuario["ativo"]:
        return False
    return usuario["role"] in ("admin", "superadmin") or "gerencia" in _normalizar(usuario["setor"])


def usuario_pode_acessar_aba(usuario, chave):
    if not usuario:
        return False
    if usuario["role"] != "comum" or usuario_eh_gestor(usuario):
        return True
    conn = _conn()
    row = conn.execute(
        "SELECT habilitada_comum FROM configuracao_abas WHERE chave = ?",
        (chave,),
    ).fetchone()
    conn.close()
    return row is None or bool(row["habilitada_comum"])


def listar_abas(usuario=None):
    conn = _conn()
    abas = conn.execute(
        "SELECT * FROM configuracao_abas ORDER BY ordem, nome"
    ).fetchall()
    conn.close()
    if usuario is None:
        return abas
    return [aba for aba in abas if usuario_pode_acessar_aba(usuario, aba["chave"])]


def salvar_abas_comuns(chaves_habilitadas):
    habilitadas = set(chaves_habilitadas or ())
    conn = _conn()
    for chave, *_ in ABAS_PADRAO:
        conn.execute(
            "UPDATE configuracao_abas SET habilitada_comum = ? WHERE chave = ?",
            (1 if chave in habilitadas else 0, chave),
        )
    conn.commit()
    conn.close()


def criar_notificacao(tipo, titulo, mensagem="", url="", referencia_tipo=None, referencia_id=None):
    conn = _conn()
    cursor = conn.execute(
        """
        INSERT INTO notificacoes(tipo, titulo, mensagem, url, referencia_tipo, referencia_id)
        VALUES(?,?,?,?,?,?)
        """,
        (tipo, titulo.strip(), mensagem.strip(), url.strip(), referencia_tipo, referencia_id),
    )
    conn.commit()
    notificacao_id = cursor.lastrowid
    conn.close()
    return notificacao_id


def criar_comunicado(titulo, mensagem, tipo, exibir_popup, link_url, inicio_em,
                     fim_em, criado_por_id, criado_por_nome):
    conn = _conn()
    cursor = conn.execute(
        """
        INSERT INTO comunicados(
            titulo, mensagem, tipo, exibir_popup, link_url, inicio_em, fim_em,
            criado_por_id, criado_por_nome
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            titulo.strip(),
            mensagem.strip(),
            tipo,
            1 if exibir_popup else 0,
            link_url.strip(),
            inicio_em or None,
            fim_em or None,
            criado_por_id,
            criado_por_nome,
        ),
    )
    comunicado_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO notificacoes(tipo, titulo, mensagem, url, referencia_tipo, referencia_id)
        VALUES(?,?,?,?,?,?)
        """,
        (
            "comunicado",
            titulo.strip(),
            mensagem.strip(),
            f"/comunicados#{comunicado_id}",
            "comunicado",
            comunicado_id,
        ),
    )
    conn.commit()
    conn.close()
    return comunicado_id


def alternar_comunicado(comunicado_id):
    conn = _conn()
    conn.execute(
        """
        UPDATE comunicados
        SET ativo = CASE ativo WHEN 1 THEN 0 ELSE 1 END,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = ? AND excluido_em IS NULL
        """,
        (comunicado_id,),
    )
    conn.commit()
    conn.close()


def excluir_comunicado(comunicado_id):
    if not comunicado_id:
        return
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _conn()
    conn.execute(
        """
        UPDATE comunicados
        SET ativo = 0,
            excluido_em = ?,
            atualizado_em = ?
        WHERE id = ?
        """,
        (agora, agora, comunicado_id),
    )
    conn.commit()
    conn.close()


def listar_comunicados(usuario_id=None, incluir_inativos=False):
    conn = _conn()
    params = [usuario_id or 0]
    where = "WHERE c.excluido_em IS NULL"
    if not incluir_inativos:
        where = """
        WHERE c.excluido_em IS NULL
          AND c.ativo = 1
          AND (c.inicio_em IS NULL OR datetime(c.inicio_em) <= datetime('now', 'localtime'))
          AND (c.fim_em IS NULL OR datetime(c.fim_em) >= datetime('now', 'localtime'))
        """
    rows = conn.execute(
        f"""
        SELECT c.*, cl.visto_em, cl.popup_fechado_em
        FROM comunicados c
        LEFT JOIN comunicado_leituras cl
          ON cl.comunicado_id = c.id AND cl.usuario_id = ?
        {where}
        ORDER BY c.criado_em DESC, c.id DESC
        """,
        params,
    ).fetchall()
    conn.close()
    return rows


def buscar_comunicado(comunicado_id, incluir_excluido=False):
    conn = _conn()
    sql = "SELECT * FROM comunicados WHERE id = ?"
    if not incluir_excluido:
        sql += " AND excluido_em IS NULL"
    row = conn.execute(sql, (comunicado_id,)).fetchone()
    conn.close()
    return row


def popup_pendente(usuario_id):
    conn = _conn()
    row = conn.execute(
        """
        SELECT c.*
        FROM comunicados c
        LEFT JOIN comunicado_leituras cl
          ON cl.comunicado_id = c.id AND cl.usuario_id = ?
        WHERE c.ativo = 1
          AND c.excluido_em IS NULL
          AND c.exibir_popup = 1
          AND cl.popup_fechado_em IS NULL
          AND (c.inicio_em IS NULL OR datetime(c.inicio_em) <= datetime('now', 'localtime'))
          AND (c.fim_em IS NULL OR datetime(c.fim_em) >= datetime('now', 'localtime'))
        ORDER BY c.criado_em, c.id
        LIMIT 1
        """,
        (usuario_id,),
    ).fetchone()
    conn.close()
    return row


def fechar_popup(comunicado_id, usuario_id):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _conn()
    conn.execute(
        """
        INSERT INTO comunicado_leituras(comunicado_id, usuario_id, visto_em, popup_fechado_em)
        VALUES(?,?,?,?)
        ON CONFLICT(comunicado_id, usuario_id) DO UPDATE SET
            visto_em = COALESCE(comunicado_leituras.visto_em, excluded.visto_em),
            popup_fechado_em = excluded.popup_fechado_em
        """,
        (comunicado_id, usuario_id, agora, agora),
    )
    conn.commit()
    conn.close()


def listar_notificacoes(usuario_id, limite=30):
    conn = _conn()
    rows = conn.execute(
        """
        SELECT n.*, nl.lida_em
        FROM notificacoes n
        LEFT JOIN notificacao_leituras nl
          ON nl.notificacao_id = n.id AND nl.usuario_id = ?
        WHERE COALESCE(n.referencia_tipo, '') != 'comunicado'
           OR EXISTS(
                SELECT 1 FROM comunicados c
                WHERE c.id = n.referencia_id
                  AND c.excluido_em IS NULL
                  AND c.ativo = 1
                  AND (c.inicio_em IS NULL OR datetime(c.inicio_em) <= datetime('now', 'localtime'))
                  AND (c.fim_em IS NULL OR datetime(c.fim_em) >= datetime('now', 'localtime'))
           )
        ORDER BY n.criado_em DESC, n.id DESC
        LIMIT ?
        """,
        (usuario_id, limite),
    ).fetchall()
    conn.close()
    return rows


def contar_nao_lidas(usuario_id):
    conn = _conn()
    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM notificacoes n
        LEFT JOIN notificacao_leituras nl
          ON nl.notificacao_id = n.id AND nl.usuario_id = ?
        WHERE nl.lida_em IS NULL
          AND (
              COALESCE(n.referencia_tipo, '') != 'comunicado'
              OR EXISTS(
                  SELECT 1 FROM comunicados c
                  WHERE c.id = n.referencia_id
                    AND c.excluido_em IS NULL
                    AND c.ativo = 1
                    AND (c.inicio_em IS NULL OR datetime(c.inicio_em) <= datetime('now', 'localtime'))
                    AND (c.fim_em IS NULL OR datetime(c.fim_em) >= datetime('now', 'localtime'))
              )
          )
        """,
        (usuario_id,),
    ).fetchone()[0]
    conn.close()
    return total


def buscar_notificacao(notificacao_id):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM notificacoes WHERE id = ?",
        (notificacao_id,),
    ).fetchone()
    conn.close()
    return row


def marcar_notificacao_lida(notificacao_id, usuario_id):
    conn = _conn()
    conn.execute(
        """
        INSERT INTO notificacao_leituras(notificacao_id, usuario_id, lida_em)
        VALUES(?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(notificacao_id, usuario_id) DO UPDATE SET lida_em = excluded.lida_em
        """,
        (notificacao_id, usuario_id),
    )
    conn.commit()
    conn.close()


def marcar_todas_lidas(usuario_id):
    conn = _conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO notificacao_leituras(notificacao_id, usuario_id, lida_em)
        SELECT n.id, ?, CURRENT_TIMESTAMP
        FROM notificacoes n
        WHERE COALESCE(n.referencia_tipo, '') != 'comunicado'
           OR EXISTS(
                SELECT 1 FROM comunicados c
                WHERE c.id = n.referencia_id
                  AND c.excluido_em IS NULL
                  AND c.ativo = 1
                  AND (c.inicio_em IS NULL OR datetime(c.inicio_em) <= datetime('now', 'localtime'))
                  AND (c.fim_em IS NULL OR datetime(c.fim_em) >= datetime('now', 'localtime'))
           )
        """,
        (usuario_id,),
    )
    conn.commit()
    conn.close()
