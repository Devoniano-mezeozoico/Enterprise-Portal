import re
import sqlite3

DB_PATH = "database/intranet.db"

def listar_noticias(limite=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM noticias ORDER BY criado_em DESC"
    params = ()
    if limite:
        sql += " LIMIT ?"
        params = (limite,)
    cursor.execute(sql, params)
    ns = cursor.fetchall()
    conn.close()
    return ns

def buscar_noticia_por_id(nid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM noticias WHERE id=?", (nid,))
    n = cursor.fetchone()
    conn.close()
    return n

def criar_noticia(titulo, resumo, conteudo, autor, caminho_anexo=None, nome_anexo=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO noticias (titulo,resumo,conteudo,autor,caminho_anexo,nome_anexo) VALUES (?,?,?,?,?,?)",
        (titulo, resumo, conteudo, autor, caminho_anexo, nome_anexo)
    )
    conn.commit()
    nid = cursor.lastrowid
    conn.close()
    return nid

def excluir_noticia(nid):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM noticias WHERE id=?", (nid,))
    conn.commit()
    conn.close()

def contar_noticias():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM noticias")
    t = cursor.fetchone()[0]
    conn.close()
    return t

def _tok(texto):
    return set(re.findall(r"[a-zà-ÿ0-9]{3,}", (texto or "").lower()))

def buscar_noticias_relevantes(pergunta, limite=2):
    termos = _tok(pergunta)
    if not termos:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM noticias")
    ns = cursor.fetchall()
    conn.close()
    pontuadas = []
    for n in ns:
        txt = f"{n['titulo']} {n['resumo'] or ''} {n['conteudo'] or ''}".lower()
        pts = sum(1 for t in termos if t in txt)
        if pts > 0:
            pontuadas.append((pts, n))
    pontuadas.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in pontuadas[:limite]]
