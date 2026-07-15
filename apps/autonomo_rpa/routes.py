import io

from flask import Blueprint, jsonify, render_template, request, send_file

from .service import gerar_arquivo_txt

bp = Blueprint(
    "autonomo_rpa",
    __name__,
    url_prefix="/apps/autonomo_rpa",
    template_folder="templates",
)

APP_INFO = {
    "nome": "Gerador RPA - Autônomos",
    "descricao": "Gera o TXT de importação de motoristas autônomos a partir da planilha de contratos.",
    "icone": "fa-solid fa-file-export",
    "url": "/apps/autonomo_rpa/",
    "setor": "Automações",
}


@bp.route("/")
def index():
    return render_template("autonomo_rpa/index.html")


@bp.route("/gerar", methods=["POST"])
def gerar():
    arquivo = request.files.get("contratos")

    if not arquivo or arquivo.filename == "":
        return jsonify(erro="Selecione a planilha de contratos."), 400

    if not arquivo.filename.lower().endswith((".xls", ".xlsx")):
        return jsonify(erro="Envie um arquivo Excel (.xls ou .xlsx)."), 400

    try:
        conteudo, total = gerar_arquivo_txt(arquivo)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    except Exception as erro:
        return jsonify(erro=f"Erro ao processar a planilha: {erro}"), 500

    buffer = io.BytesIO(conteudo.encode("utf-8"))
    buffer.seek(0)

    resposta = send_file(
        buffer,
        as_attachment=True,
        download_name="autonomoRPA_importar.txt",
        mimetype="text/plain"
    )
    resposta.headers["X-Total-Exportados"] = str(total)
    resposta.headers["Access-Control-Expose-Headers"] = "X-Total-Exportados"
    return resposta
