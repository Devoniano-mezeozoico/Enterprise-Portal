"""Redefine com segurança a senha de um admin/superadmin existente.

O utilitário nunca cria, exclui, promove ou reativa usuários. Antes da única
alteração autorizada (senha_hash), cria e verifica um backup consistente do
banco e registra a operação na auditoria, sem armazenar a senha.
"""

import argparse
import getpass
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv(ROOT / ".env")

from database.connection import connect_db, database_path
from database.models import auditoria as auditoria_model


PAPEIS_ADMINISTRATIVOS = {"admin", "superadmin"}


def _backup_verificado(source_path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = source_path.with_name(
        f"{source_path.stem}.before_password_reset_{stamp}{source_path.suffix}"
    )
    source = sqlite3.connect(str(source_path), timeout=30)
    backup = sqlite3.connect(str(backup_path))
    try:
        source.execute("PRAGMA busy_timeout=30000")
        source.backup(backup)
    finally:
        backup.close()
        source.close()

    verifier = sqlite3.connect(str(backup_path))
    try:
        if verifier.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("O backup da base não passou na verificação de integridade.")
    finally:
        verifier.close()
    return backup_path


def listar_administradores():
    conn = connect_db(readonly=True)
    try:
        return conn.execute(
            """
            SELECT id, nome, email, role, ativo, excluido_em
              FROM usuarios
             WHERE role IN ('admin', 'superadmin')
             ORDER BY role DESC, nome
            """
        ).fetchall()
    finally:
        conn.close()


def _senha_informada():
    senha = getpass.getpass("Nova senha temporária: ")
    confirmacao = getpass.getpass("Repita a nova senha: ")
    if senha != confirmacao:
        raise ValueError("As senhas informadas não coincidem.")
    if len(senha) < 12:
        raise ValueError("Use pelo menos 12 caracteres.")
    return senha


def redefinir_senha(email, senha, *, operador=None):
    source_path = database_path().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Banco não encontrado: {source_path}")
    if len(senha) < 12:
        raise ValueError("Use pelo menos 12 caracteres.")

    consulta = connect_db(readonly=True)
    try:
        usuario = consulta.execute(
            """
            SELECT id, nome, email, role, setor, ativo, excluido_em
              FROM usuarios
             WHERE lower(email) = lower(?)
            """,
            ((email or "").strip(),),
        ).fetchone()
    finally:
        consulta.close()

    if not usuario:
        raise ValueError("Usuário não encontrado; nenhuma alteração foi feita.")
    if usuario["role"] not in PAPEIS_ADMINISTRATIVOS:
        raise ValueError("A conta não é admin/superadmin; nenhuma alteração foi feita.")
    if not usuario["ativo"] or usuario["excluido_em"] is not None:
        raise ValueError("A conta está inativa ou removida; nenhuma alteração foi feita.")

    backup_path = _backup_verificado(source_path)
    conn = connect_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE usuarios
               SET senha_hash = ?
             WHERE id = ? AND ativo = 1 AND excluido_em IS NULL
            """,
            (generate_password_hash(senha), usuario["id"]),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("A conta mudou durante a operação; redefinição cancelada.")
        auditoria_model.registrar_evento(
            acao="redefinir_senha_emergencial",
            modulo="usuarios",
            registro_id=usuario["id"],
            anterior={"id": usuario["id"], "email": usuario["email"], "senha_alterada": False},
            novo={"id": usuario["id"], "email": usuario["email"], "senha_alterada": True},
            detalhes={
                "origem": "scripts/reset_admin_password.py",
                "operador_sistema": operador or getpass.getuser(),
            },
            user_agent="manutencao-local",
            conexao=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return backup_path, usuario


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Redefine somente a senha de um admin/superadmin ativo."
    )
    parser.add_argument("email", nargs="?", help="E-mail exato da conta administrativa")
    parser.add_argument(
        "--gerar",
        action="store_true",
        help="Gera uma senha forte e a exibe uma única vez, em vez de solicitá-la.",
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="Lista contas administrativas sem exibir hashes ou senhas.",
    )
    args = parser.parse_args(argv)

    if args.listar:
        for usuario in listar_administradores():
            estado = "ativo" if usuario["ativo"] and usuario["excluido_em"] is None else "inativo"
            print(f"{usuario['email']} | {usuario['role']} | {estado}")
        return 0

    email = (args.email or input("E-mail do admin/superadmin: ")).strip()
    senha = secrets.token_urlsafe(18) if args.gerar else _senha_informada()
    backup, usuario = redefinir_senha(email, senha)
    print(f"Backup verificado: {backup}")
    print(f"Senha redefinida somente para: {usuario['email']} ({usuario['role']})")
    if args.gerar:
        print(f"Senha temporária (exibida uma vez): {senha}")
    print("Entre no portal e substitua a senha temporária por uma senha corporativa.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
