import hmac
import secrets
from urllib.parse import urlparse

from flask import current_app, flash, jsonify, redirect, request, session, url_for


CSRF_SESSION_KEY = "_csrf_token"


def get_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(token):
    expected = session.get(CSRF_SESSION_KEY)
    return bool(expected and token and hmac.compare_digest(str(expected), str(token)))


def csrf_exempt(view):
    view._csrf_exempt = True
    return view


def _csrf_failure():
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(erro="Token CSRF inválido ou ausente."), 400
    session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    flash(
        "Sua página estava com um token de segurança antigo. Tente enviar novamente.",
        "erro",
    )
    destino = request.referrer or url_for("home")
    try:
        parsed = urlparse(destino)
        if parsed.netloc and parsed.netloc != request.host:
            destino = url_for("home")
    except Exception:
        destino = url_for("home")
    return redirect(destino)


def _request_is_exempt():
    endpoint = request.endpoint or ""
    view = current_app.view_functions.get(endpoint)
    if getattr(view, "_csrf_exempt", False):
        return True

    exempt_endpoints = current_app.config.get("CSRF_EXEMPT_ENDPOINTS", set())
    if endpoint in exempt_endpoints:
        return True

    exempt_prefixes = current_app.config.get("CSRF_EXEMPT_PREFIXES", ())
    return any(request.path.startswith(prefix) for prefix in exempt_prefixes)


def install_security(app):
    app.jinja_env.globals["csrf_token"] = get_csrf_token

    @app.before_request
    def csrf_protect():
        if not app.config.get("WTF_CSRF_ENABLED", True):
            return None
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        if _request_is_exempt():
            return None
        token = (
            request.form.get("_csrf_token")
            or request.headers.get("X-CSRFToken")
            or request.headers.get("X-CSRF-Token")
        )
        if not validate_csrf_token(token):
            return _csrf_failure()
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response

    return app
