import importlib.util
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash

from conftest import db_path


def _carregar_script():
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "reset_admin_password.py"
    spec = importlib.util.spec_from_file_location("reset_admin_password", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_reset_admin_password_changes_only_hash_and_audits(portal_app, monkeypatch):
    caminho_banco = db_path(portal_app)
    monkeypatch.setenv("DATABASE_PATH", str(caminho_banco))
    script = _carregar_script()

    conn = sqlite3.connect(caminho_banco)
    conn.row_factory = sqlite3.Row
    usuario = conn.execute(
        "SELECT * FROM usuarios WHERE ativo=1 AND excluido_em IS NULL "
        "AND role IN ('admin','superadmin') LIMIT 1"
    ).fetchone()
    anterior = dict(usuario)
    conn.close()

    backup, alterado = script.redefinir_senha(
        usuario["email"], "Temporaria-Segura-2026", operador="pytest"
    )

    assert backup.is_file()
    conn = sqlite3.connect(caminho_banco)
    conn.row_factory = sqlite3.Row
    atual = conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario["id"],)).fetchone()
    for campo in anterior:
        if campo != "senha_hash":
            assert atual[campo] == anterior[campo]
    assert atual["senha_hash"] != anterior["senha_hash"]
    assert check_password_hash(atual["senha_hash"], "Temporaria-Segura-2026")
    evento = conn.execute(
        "SELECT * FROM auditoria_eventos WHERE modulo='usuarios' "
        "AND acao='redefinir_senha_emergencial' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert evento is not None
    assert evento["registro_id"] == str(alterado["id"])
    assert "Temporaria-Segura-2026" not in (evento["dados_novos"] or "")
    assert "Temporaria-Segura-2026" not in (evento["detalhes"] or "")
    conn.close()
    assert script.auditoria_model.verificar_integridade() == (True, None)


def test_reset_refuses_common_or_inactive_accounts(portal_app, monkeypatch):
    caminho_banco = db_path(portal_app)
    monkeypatch.setenv("DATABASE_PATH", str(caminho_banco))
    script = _carregar_script()
    conn = sqlite3.connect(caminho_banco)
    comum = conn.execute("SELECT email FROM usuarios WHERE role='comum' LIMIT 1").fetchone()
    conn.close()
    if comum:
        try:
            script.redefinir_senha(comum[0], "Temporaria-Segura-2026")
        except ValueError as exc:
            assert "não é admin/superadmin" in str(exc)
        else:
            raise AssertionError("Conta comum não pode ser redefinida por este utilitário")

    conn = sqlite3.connect(caminho_banco)
    admin = conn.execute(
        "SELECT id,email,senha_hash FROM usuarios WHERE role IN ('admin','superadmin') LIMIT 1"
    ).fetchone()
    conn.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (admin[0],))
    conn.commit()
    conn.close()
    try:
        script.redefinir_senha(admin[1], "Temporaria-Segura-2026")
    except ValueError as exc:
        assert "inativa ou removida" in str(exc)
    else:
        raise AssertionError("Conta administrativa inativa não pode ser reativada implicitamente")

    conn = sqlite3.connect(caminho_banco)
    assert conn.execute("SELECT senha_hash FROM usuarios WHERE id=?", (admin[0],)).fetchone()[0] == admin[2]
    conn.close()
