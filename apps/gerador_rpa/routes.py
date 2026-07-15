from flask import Blueprint, jsonify, render_template, request

from .service import gerar_script_rpa

bp = Blueprint(
    "gerador_rpa",
    __name__,
    url_prefix="/apps/gerador_rpa",
    template_folder="templates",
)

APP_INFO = {
    "nome": "Gerador de RPA",
    "descricao": "Cria scripts de automação a partir de uma lista de passos.",
    "icone": "fa-solid fa-robot",
    "url": "/apps/gerador_rpa/",
    "setor": "Automações",
}


@bp.route("/")
def index():
    return render_template("gerador_rpa/index.html")


@bp.route("/gerar", methods=["POST"])
def gerar():
    dados = request.get_json(silent=True) or {}
    nome_processo = dados.get("nome_processo", "")
    passos = dados.get("passos", [])

    if isinstance(passos, str):
        passos = [linha for linha in passos.splitlines() if linha.strip()]

    script = gerar_script_rpa(nome_processo, passos)
    return jsonify(sucesso=True, script=script)
