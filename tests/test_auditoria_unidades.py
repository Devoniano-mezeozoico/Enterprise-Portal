import sqlite3

import pytest

from conftest import db_path, fetch_user_id, login_as, post_form


def test_migration_is_additive_and_does_not_classify_legacy_rows(portal_app):
    conn = sqlite3.connect(db_path(portal_app))
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    remoto = conn.execute(
        "SELECT id,nome,eh_remoto FROM unidades WHERE codigo='REMOTO'"
    ).fetchone()
    assert remoto is not None
    assert remoto[1] == "Remoto"
    assert remoto[2] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM usuario_unidades WHERE unidade_id=?", (remoto[0],)
    ).fetchone()[0] == 0
    conn.close()


def test_audit_records_actor_and_is_immutable(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo=1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    response = post_form(
        client,
        "/comunicados",
        {"acao": "criar", "titulo": "Auditoria pytest", "mensagem": "Evento rastreável."},
    )
    assert response.status_code == 302

    conn = sqlite3.connect(db_path(portal_app))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM auditoria_eventos WHERE modulo='comunicados' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["usuario_id"] == admin_id
    assert row["acao"] == "criar"
    assert row["integridade_hash"]
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE auditoria_eventos SET acao='alterado' WHERE id=?", (row["id"],))
    conn.rollback()
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM auditoria_eventos WHERE id=?", (row["id"],))
    conn.close()


def test_soft_delete_preserves_app_record_and_id(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo=1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    response = post_form(
        client,
        "/admin/apps",
        {
            "acao": "criar",
            "nome": "App preservado pytest",
            "descricao": "Teste",
            "icone": "fa-solid fa-flask",
            "url": "/",
            "setor": "TI",
            "setores_liberados": "TI",
        },
    )
    assert response.status_code == 302
    conn = sqlite3.connect(db_path(portal_app))
    app_id = conn.execute("SELECT id FROM hub_apps WHERE nome='App preservado pytest'").fetchone()[0]
    conn.close()

    response = post_form(client, "/admin/apps", {"acao": "excluir", "app_id": app_id})
    assert response.status_code == 302
    conn = sqlite3.connect(db_path(portal_app))
    row = conn.execute("SELECT id, ativo, excluido_em FROM hub_apps WHERE id=?", (app_id,)).fetchone()
    assert row[0] == app_id
    assert row[1] == 0
    assert row[2] is not None
    assert conn.execute(
        "SELECT COUNT(*) FROM auditoria_eventos WHERE modulo='hub_apps' AND registro_id=?",
        (str(app_id),),
    ).fetchone()[0] >= 2
    conn.close()


def test_new_atendimento_import_archives_previous_metrics(portal_app):
    conn = sqlite3.connect(db_path(portal_app))
    before = conn.execute("SELECT COUNT(*) FROM atendimento_metricas").fetchone()[0]
    conn.close()
    linhas = [{
        "nome": "Pytest",
        "departamento": "TI",
        "qtd_atendimentos": 1,
        "tempo_medio_segundos": 60,
        "tempo_medio_formatado": "00:01:00",
        "satisfeitos": 1,
        "nao_satisfeitos": 0,
        "total_pesquisa": 1,
        "satisfacao_percentual": 100.0,
    }]
    importacao_id = portal_app.atendimentos_model.salvar_metricas(
        linhas, "pytest.xlsx", "resultado", usuario_id=None, usuario_nome="Pytest"
    )
    conn = sqlite3.connect(db_path(portal_app))
    assert conn.execute("SELECT COUNT(*) FROM atendimento_metricas").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM atendimento_metricas_historico WHERE importacao_id=?",
        (importacao_id,),
    ).fetchone()[0] == before
    conn.close()


def test_new_admin_pages_and_existing_navigation_render(client, portal_app):
    superadmin_id = fetch_user_id(portal_app, "ativo=1 AND role='superadmin'")
    login_as(client, superadmin_id)
    expected = {
        "/": b"Intranet",
        "/agenda": b"Agenda",
        "/admin/usuarios": b"Unidade",
        "/admin/atendimentos": b"hist",
        "/admin/unidades": b"Filial",
        "/admin/auditoria": b"Auditoria",
    }
    for path, marker in expected.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert marker.lower() in response.data.lower(), path


def test_common_user_cannot_open_audit_page(client, portal_app):
    common_id = fetch_user_id(portal_app, "ativo=1 AND role='comum'")
    if common_id is None:
        return
    login_as(client, common_id)
    response = client.get("/admin/auditoria")
    assert response.status_code == 302


def test_ticket_without_location_is_created_without_server_error(client, portal_app):
    user_id = fetch_user_id(portal_app, "ativo=1 AND role='comum'")
    if user_id is None:
        user_id = fetch_user_id(portal_app, "ativo=1")
    portal_app.unidades_model.vincular_usuario(user_id, None)
    assert portal_app.unidades_model.unidade_do_usuario(user_id) is None
    login_as(client, user_id)

    response = post_form(
        client,
        "/ti/chamados",
        {
            "titulo": "Chamado sem local pytest",
            "descricao": "Não deve gerar erro 500.",
            "prioridade": "normal",
        },
    )
    assert response.status_code == 302
    conn = sqlite3.connect(db_path(portal_app))
    chamado = conn.execute(
        "SELECT id FROM chamados_ti WHERE titulo='Chamado sem local pytest' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert chamado is not None
    vinculo = conn.execute(
        "SELECT unidade_id,escopo FROM registro_unidades "
        "WHERE modulo='chamados_ti' AND registro_id=?",
        (str(chamado[0]),),
    ).fetchone()
    assert vinculo == (None, "nao_definido")
    conn.close()


def test_remote_user_ticket_inherits_remote_location(client, portal_app):
    user_id = fetch_user_id(portal_app, "ativo=1 AND role='comum'")
    if user_id is None:
        user_id = fetch_user_id(portal_app, "ativo=1")
    conn = sqlite3.connect(db_path(portal_app))
    remoto_id = conn.execute("SELECT id FROM unidades WHERE codigo='REMOTO'").fetchone()[0]
    conn.close()
    portal_app.unidades_model.vincular_usuario(user_id, remoto_id)
    login_as(client, user_id)

    response = post_form(
        client,
        "/ti/chamados",
        {
            "titulo": "Chamado remoto pytest",
            "descricao": "Local remoto herdado.",
            "prioridade": "alta",
        },
    )
    assert response.status_code == 302
    conn = sqlite3.connect(db_path(portal_app))
    chamado_id = conn.execute(
        "SELECT id FROM chamados_ti WHERE titulo='Chamado remoto pytest' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    vinculo = conn.execute(
        "SELECT unidade_id,escopo FROM registro_unidades "
        "WHERE modulo='chamados_ti' AND registro_id=?",
        (str(chamado_id),),
    ).fetchone()
    assert vinculo == (remoto_id, "unidade")
    conn.close()


def test_ticket_creation_rolls_back_if_location_link_fails(portal_app):
    user_id = fetch_user_id(portal_app, "ativo=1")
    conn = sqlite3.connect(db_path(portal_app))
    before = conn.execute("SELECT COUNT(*) FROM chamados_ti").fetchone()[0]
    conn.close()

    with pytest.raises(sqlite3.IntegrityError):
        portal_app.chamados_model.criar_chamado(
            user_id,
            "Pytest",
            "Chamado que deve voltar atrás",
            "Unidade inexistente.",
            unidade_id=999999999,
            associado_por_id=user_id,
        )

    conn = sqlite3.connect(db_path(portal_app))
    assert conn.execute("SELECT COUNT(*) FROM chamados_ti").fetchone()[0] == before
    conn.close()
