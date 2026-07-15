import importlib
import os
import sys

import pytest

from conftest import csrf_token, fetch_user_id, login_as, post_form


def test_secret_key_does_not_use_fixed_fallback(portal_app):
    assert portal_app.app.config["SECRET_KEY"] != "empresa_intranet_2026"
    assert portal_app.app.config["SECRET_KEY"] == "pytest-secret-key"


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    sys.modules.pop("config", None)
    with pytest.raises(RuntimeError):
        importlib.import_module("config")


def test_csrf_recovers_plain_form_post_with_redirect(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    response = client.post(
        "/comunicados",
        data={"acao": "criar", "titulo": "Sem CSRF", "mensagem": "Bloquear"},
    )
    assert response.status_code == 302


def test_csrf_accepts_valid_form_post(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    response = post_form(
        client,
        "/comunicados",
        {
            "acao": "criar",
            "titulo": "Com CSRF",
            "mensagem": "Aceito pela protecao CSRF.",
            "tipo": "informacao",
        },
    )
    assert response.status_code == 302


def test_security_headers_are_present(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "strict-origin" in response.headers["Referrer-Policy"]


def test_service_worker_route_has_safe_scope(client):
    response = client.get("/portal-notifications-sw.js")
    assert response.status_code == 200
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert b"notificationclick" in response.data


def test_mutating_json_api_requires_csrf(client, portal_app):
    admin_id = fetch_user_id(portal_app, "ativo = 1 AND role IN ('admin','superadmin')")
    login_as(client, admin_id)
    denied = client.post("/api/chat/enviar", json={"mensagem": "sem token"})
    assert denied.status_code == 400
    accepted = client.post(
        "/api/chat/enviar",
        json={"mensagem": "com token"},
        headers={"X-CSRFToken": csrf_token(client)},
    )
    assert accepted.status_code == 200
