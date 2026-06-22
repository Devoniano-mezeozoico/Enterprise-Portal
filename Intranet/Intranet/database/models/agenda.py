import re
import sqlite3

DB_PATH = "database/intranet.db"

PALETA_SALAS = [
    "#2E7D52","#0d6efd","#fd7e14","#6f42c1",
    "#20c997","#d63384","#0dcaf0","#dc3545",
    "#ffc107","#6610f2","#198754","#6c757d",
]

def cor_da_sala(sala):
    idx = sum(ord(c) for c in (sala or "")) % len(PALETA_SALAS)
    return PALETA_SALAS[idx]

def listar_eventos_mes(ano, mes):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM eventos_agenda WHERE strftime('%Y',data_evento)=? AND strftime('%m',data_evento)=? ORDER BY data_evento,hora_inicio",
        (str(ano), f"{mes:02d}")
    )
    eventos = cursor.fetchall()
    conn.close()
    return eventos

def buscar_evento_por_id(eid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos_agenda WHERE id=?", (eid,))
    e = cursor.fetchone()
    conn.close()
    return e

def criar_evento(titulo, descricao, data_evento, hora_inicio, hora_fim, sala, criado_por):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO eventos_agenda (titulo,descricao,data_evento,hora_inicio,hora_fim,sala,criado_por) VALUES (?,?,?,?,?,?,?)",
        (titulo, descricao, data_evento, hora_inicio, hora_fim, sala, criado_por)
    )
    conn.commit()
    eid = cursor.lastrowid
    conn.close()
    return eid

def atualizar_evento(eid, titulo, descricao, data_evento, hora_inicio, hora_fim, sala):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE eventos_agenda SET titulo=?,descricao=?,data_evento=?,hora_inicio=?,hora_fim=?,sala=? WHERE id=?",
        (titulo, descricao, data_evento, hora_inicio, hora_fim, sala, eid)
    )
    conn.commit()
    conn.close()

def excluir_evento(eid):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM eventos_agenda WHERE id=?", (eid,))
    conn.commit()
    conn.close()

def listar_salas_em_uso():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT sala FROM eventos_agenda ORDER BY sala")
    salas = [r[0] for r in cursor.fetchall()]
    conn.close()
    return salas

def _tok(texto):
    return set(re.findall(r"[a-zà-ÿ0-9]{3,}", (texto or "").lower()))

def buscar_eventos_relevantes(pergunta, limite=3):
    termos = _tok(pergunta)
    if not termos:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos_agenda WHERE data_evento >= date('now') ORDER BY data_evento")
    eventos = cursor.fetchall()
    conn.close()
    pontuados = []
    for e in eventos:
        txt = f"{e['titulo']} {e['descricao'] or ''} {e['sala']}".lower()
        pts = sum(1 for t in termos if t in txt)
        if pts > 0:
            pontuados.append((pts, e))
    pontuados.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in pontuados[:limite]]
