from flask import Blueprint, render_template

bp = Blueprint(
    "fiscal",
    __name__,
    url_prefix="/apps/fiscal",
    template_folder="templates",
)

APP_INFO = {
    "nome": "Dashboard Fiscal",
    "descricao": "Indicadores e conferências fiscais (SAT, CT-e, NF-e).",
    "icone": "fa-solid fa-file-invoice-dollar",
    "url": "/apps/fiscal/dashboard",
    "setor": "Fiscal",
}


@bp.route("/dashboard")
def dashboard():
    return render_template("fiscal/dashboard.html")
