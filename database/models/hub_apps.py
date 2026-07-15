"""
Modelo para o Hub de Aplicativos — apps são registros no banco,
apontando para qualquer URL (interna ou externa). Admins cadastram
e removem apps pelo painel /admin/apps.
"""
import os
import sqlite3
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH
SETOR_GLOBAL = {"", "todos", "todo", "geral", "global"}


def _norm(texto):
    return (texto or "").strip().lower()


def _setores_permitidos(app):
    valor = ""
    try:
        valor = app["setores_liberados"]
    except (KeyError, IndexError):
        valor = ""
    if not valor:
        valor = app["setor"]
    return {_norm(parte) for parte in str(valor or "").replace(";", ",").split(",")}


def app_visivel_para_usuario(app, usuario):
    if not usuario:
        return False
    if usuario["role"] in ("admin", "superadmin"):
        return True
    setor_usuario = _norm(usuario["setor"])
    setores = _setores_permitidos(app)
    if setores & SETOR_GLOBAL:
        return True
    return bool(setor_usuario and setor_usuario in setores)


def listar_apps(apenas_ativos=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM hub_apps WHERE excluido_em IS NULL"
    if apenas_ativos:
        sql += " AND ativo = 1"
    sql += " ORDER BY setor, nome"
    cursor.execute(sql)
    apps = cursor.fetchall()
    conn.close()
    return apps


def listar_apps_para_usuario(usuario, apenas_ativos=True):
    apps = listar_apps(apenas_ativos)
    return [app for app in apps if app_visivel_para_usuario(app, usuario)]


def listar_apps_por_setor(apenas_ativos=True):
    apps = listar_apps(apenas_ativos)
    setores = {}
    for app in apps:
        setores.setdefault(app["setor"], []).append(app)
    return setores


def listar_apps_por_setor_para_usuario(usuario, apenas_ativos=True):
    apps = listar_apps_para_usuario(usuario, apenas_ativos)
    setores = {}
    for app in apps:
        setores.setdefault(app["setor"], []).append(app)
    return setores


def contar_apps(usuario=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hub_apps WHERE ativo = 1 AND excluido_em IS NULL")
    apps = cursor.fetchall()
    conn.close()
    if usuario is None or usuario["role"] in ("admin", "superadmin"):
        return len(apps)
    return len([app for app in apps if app_visivel_para_usuario(app, usuario)])


def buscar_app_por_id(app_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hub_apps WHERE id = ? AND excluido_em IS NULL", (app_id,))
    app = cursor.fetchone()
    conn.close()
    return app


def criar_app(nome, descricao, icone, url, setor, setores_liberados=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO hub_apps (nome, descricao, icone, url, setor, setores_liberados) VALUES (?, ?, ?, ?, ?, ?)",
        (
            nome.strip(),
            descricao.strip(),
            icone.strip(),
            url.strip(),
            setor.strip(),
            (setores_liberados if setores_liberados is not None else setor).strip(),
        )
    )
    conn.commit()
    app_id = cursor.lastrowid
    conn.close()
    return app_id


def atualizar_app(app_id, nome, descricao, icone, url, setor, setores_liberados=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    liberados = (setores_liberados if setores_liberados is not None else setor).strip()
    cursor.execute(
        """UPDATE hub_apps
           SET nome = ?, descricao = ?, icone = ?, url = ?, setor = ?, setores_liberados = ?
           WHERE id = ?""",
        (
            nome.strip(),
            descricao.strip(),
            icone.strip(),
            url.strip(),
            setor.strip(),
            liberados,
            app_id,
        )
    )
    conn.commit()
    conn.close()


def excluir_app(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE hub_apps SET ativo=0, excluido_em=COALESCE(excluido_em, CURRENT_TIMESTAMP) WHERE id = ?",
        (app_id,),
    )
    conn.commit()
    conn.close()


def alternar_ativo(app_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE hub_apps SET ativo = NOT ativo WHERE id = ? AND excluido_em IS NULL", (app_id,))
    conn.commit()
    conn.close()


def contar_por_tabela():
    """Retorna total de apps cadastrados (ativos e inativos)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM hub_apps WHERE excluido_em IS NULL")
    total = cursor.fetchone()[0]
    conn.close()
    return total
