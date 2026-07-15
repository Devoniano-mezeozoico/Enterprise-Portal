from datetime import datetime, timedelta
import sqlite3

from conftest import db_path, fetch_user_id, login_as, post_form


def test_realtime_api_and_scheduled_popup_flow(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)

    response = client.get("/api/portal/tempo-real?path=/")
    assert response.status_code == 200
    for key in ("nao_lidas", "notificacoes", "popup", "abas", "versao", "poll_ms"):
        assert key in response.json

    future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    title = "Popup agendado pytest"
    response = post_form(
        client,
        "/comunicados",
        {
            "acao": "criar",
            "titulo": title,
            "mensagem": "Validacao automatizada.",
            "tipo": "atencao",
            "exibir_popup": "1",
            "inicio_em": future,
        },
    )
    assert response.status_code == 302

    conn = sqlite3.connect(db_path(portal_app))
    row = conn.execute("SELECT id FROM comunicados WHERE titulo = ?", (title,)).fetchone()
    scheduled_id = row[0]
    conn.close()

    payload = client.get("/api/portal/tempo-real?path=/").json
    assert not payload["popup"] or payload["popup"]["id"] != scheduled_id
    assert all(item["titulo"] != title for item in payload["notificacoes"])

    past = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path(portal_app))
    conn.execute(
        "UPDATE comunicados SET inicio_em = ?, atualizado_em = CURRENT_TIMESTAMP WHERE id = ?",
        (past, scheduled_id),
    )
    conn.commit()
    conn.close()

    payload = client.get("/api/portal/tempo-real?path=/").json
    assert payload["popup"]["id"] == scheduled_id
    assert any(item["titulo"] == title for item in payload["notificacoes"])


def test_common_user_tab_block_is_reported_realtime(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    common_id = fetch_user_id(portal_app, "ativo = 1 AND role = 'comum'")
    if common_id is None:
        conn = sqlite3.connect(db_path(portal_app))
        cursor = conn.execute(
            """
            INSERT INTO usuarios(nome,email,senha_hash,role,setor,ativo)
            VALUES('Usuario Pytest','pytest-comum@empresa.local','teste','comum','Operacional',1)
            """
        )
        common_id = cursor.lastrowid
        conn.commit()
        conn.close()

    login_as(client, admin_id)
    enabled_except_ia = [
        key for key, *_ in portal_app.comunicados_model.ABAS_PADRAO if key != "ia"
    ]
    response = post_form(
        client,
        "/comunicados",
        {"acao": "salvar_abas", "abas_habilitadas": enabled_except_ia},
    )
    assert response.status_code == 302

    login_as(client, common_id)
    response = client.get("/api/portal/tempo-real?path=/ia")
    assert response.status_code == 200
    assert response.json["acesso_atual"] is False
    assert all(aba["chave"] != "ia" for aba in response.json["abas"])
