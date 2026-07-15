from functools import wraps
from flask import flash, jsonify, redirect, request, session, url_for
from database.models import usuarios as usuarios_model

ORDEM_PAPEIS = {"comum": 0, "recepcao": 1, "admin": 2, "superadmin": 3}

def usuario_atual():
    uid = session.get("usuario_id")
    return usuarios_model.buscar_usuario_por_id(uid) if uid else None

def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        uid = session.get("usuario_id")
        if not uid:
            if request.path.startswith("/api/"):
                return jsonify(erro="Não autenticado."), 401
            flash("Faça login para continuar.", "erro")
            return redirect(url_for("login", proximo=request.path))
        u = usuarios_model.buscar_usuario_por_id(uid)
        if not u or not u["ativo"]:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper

def papel_minimo(papel_exigido):
    def decorador(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            uid = session.get("usuario_id")
            if not uid:
                if request.path.startswith("/api/"):
                    return jsonify(erro="Não autenticado."), 401
                flash("Faça login para continuar.", "erro")
                return redirect(url_for("login", proximo=request.path))
            u = usuarios_model.buscar_usuario_por_id(uid)
            nivel = ORDEM_PAPEIS.get(u["role"], 0) if u else -1
            if not u or not u["ativo"] or nivel < ORDEM_PAPEIS[papel_exigido]:
                if request.path.startswith("/api/"):
                    return jsonify(erro="Permissão insuficiente."), 403
                flash("Você não tem permissão para acessar essa página.", "erro")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapper
    return decorador

# Atalhos
recepcao_required = papel_minimo("recepcao")   # recepcao, admin, superadmin
admin_required    = papel_minimo("admin")       # admin, superadmin
superadmin_required = papel_minimo("superadmin")
