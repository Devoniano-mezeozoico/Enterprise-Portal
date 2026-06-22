"""
Modelo para o Hub de Aplicativos — apps são registros no banco,
apontando para qualquer URL (interna ou externa). Admins cadastram
e removem apps pelo painel /admin/apps.
"""
import sqlite3

DB_PATH = "database/intranet.db"


def listar_apps(apenas_ativos=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM hub_apps"
    if apenas_ativos:
        sql += " WHERE ativo = 1"
    sql += " ORDER BY setor, nome"
    cursor.execute(sql)
    apps = cursor.fetchall()
    conn.close()
    return apps


def listar_apps_por_setor(apenas_ativos=True):
    apps = listar_apps(apenas_ativos)
    setores = {}
    for app in apps:
        setores.setdefault(app["setor"], []).append(app)
    return setores


def contar_apps():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM hub_apps WHERE ativo = 1")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def buscar_app_por_id(app_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hub_apps WHERE id = ?", (app_id,))
    app = cursor.fetchone()
    conn.close()
    return app


def criar_app(nome, descricao, icone, url, setor):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO hub_apps (nome, descricao, icone, url, setor) VALUES (?, ?, ?, ?, ?)",
        (nome.strip(), descricao.strip(), icone.strip(), url.strip(), setor.strip())
    )
    conn.commit()
    app_id = cursor.lastrowid
    conn.close()
    return app_id


def excluir_app(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM hub_apps WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()


def alternar_ativo(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE hub_apps SET ativo = NOT ativo WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()


def contar_por_tabela():
    """Retorna total de apps cadastrados (ativos e inativos)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM hub_apps")
    total = cursor.fetchone()[0]
    conn.close()
    return total
