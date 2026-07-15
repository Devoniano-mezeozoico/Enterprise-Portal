import os
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH
PAPEIS = ("comum", "recepcao", "admin", "superadmin")


def criar_usuario(nome, email, senha, role="comum", setor=None):
    if role not in PAPEIS:
        raise ValueError("Papel inválido.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usuarios (nome, email, senha_hash, role, setor) VALUES (?, ?, ?, ?, ?)",
        (nome.strip(), email.lower().strip(), generate_password_hash(senha), role, setor)
    )
    conn.commit()
    uid = cursor.lastrowid
    conn.close()
    return uid

def buscar_usuario_por_email(email, incluir_excluido=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    sql = "SELECT * FROM usuarios WHERE email = ?"
    if not incluir_excluido:
        sql += " AND excluido_em IS NULL"
    cursor.execute(sql, (email.lower().strip(),))
    u = cursor.fetchone()
    conn.close()
    return u

def buscar_usuario_por_id(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ? AND excluido_em IS NULL", (uid,))
    u = cursor.fetchone()
    conn.close()
    return u

def verificar_senha(usuario, senha):
    return check_password_hash(usuario["senha_hash"], senha)

def listar_usuarios():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id,nome,email,role,setor,ativo,criado_em FROM usuarios WHERE excluido_em IS NULL ORDER BY nome")
    us = cursor.fetchall()
    conn.close()
    return us

def atualizar_usuario(uid, nome, email, role, setor, senha=None):
    if role not in PAPEIS:
        raise ValueError("Papel invalido.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if senha:
        cursor.execute(
            "UPDATE usuarios SET nome=?, email=?, role=?, setor=?, senha_hash=? WHERE id=?",
            (nome.strip(), email.lower().strip(), role, (setor or "").strip(), generate_password_hash(senha), uid)
        )
    else:
        cursor.execute(
            "UPDATE usuarios SET nome=?, email=?, role=?, setor=? WHERE id=?",
            (nome.strip(), email.lower().strip(), role, (setor or "").strip(), uid)
        )
    conn.commit()
    conn.close()

def atualizar_role(uid, role):
    if role not in PAPEIS:
        raise ValueError("Papel inválido.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET role=? WHERE id=?", (role, uid))
    conn.commit()
    conn.close()

def atualizar_status(uid, ativo):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET ativo=? WHERE id=?", (1 if ativo else 0, uid))
    conn.commit()
    conn.close()

def excluir_usuario(uid):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE usuarios SET ativo=0, excluido_em=COALESCE(excluido_em, CURRENT_TIMESTAMP) WHERE id=?",
        (uid,),
    )
    conn.commit()
    conn.close()

def contar_usuarios():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE excluido_em IS NULL")
    t = cursor.fetchone()[0]
    conn.close()
    return t
