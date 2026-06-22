from flask import Blueprint, render_template_string

bp = Blueprint(
    "rh",
    __name__,
    url_prefix="/apps/rh",
)

APP_INFO = {
    "nome": "Treinamentos",
    "descricao": "Trilhas de treinamento e capacitação dos colaboradores.",
    "icone": "fa-solid fa-graduation-cap",
    "url": "/apps/rh/treinamentos",
    "setor": "RH",
}

_PAGINA = """
{% extends "base.html" %}
{% block title %}Treinamentos{% endblock %}
{% block content %}
<div class="page-title">
    <h1>Treinamentos</h1>
    <p>Trilhas de capacitação do setor de Recursos Humanos.</p>
</div>
<div class="card">
    <p>Em breve esta página listará os treinamentos disponíveis para os colaboradores.</p>
</div>
{% endblock %}
"""


@bp.route("/treinamentos")
def treinamentos():
    return render_template_string(_PAGINA)
