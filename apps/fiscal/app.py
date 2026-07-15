from __future__ import annotations

import os
import re
import secrets
import shutil
import time
import uuid
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file, url_for
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from conferencia_core import (
    ConferenciaError,
    dependency_warnings,
    exportar_documento,
    exportar_teste,
    processar_documento,
    processar_teste,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
UPLOAD_ROOT = Path(os.environ.get("FISCAL_UPLOAD_DIR", BASE_DIR / "instance" / "uploads"))
RESULT_ROOT = Path(os.environ.get("FISCAL_RESULT_DIR", BASE_DIR / "instance" / "results"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("FISCAL_MAX_UPLOAD_MB", "256")) * 1024 * 1024


def ensure_dirs() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_old_files(max_age_seconds: int = 24 * 60 * 60) -> None:
    ensure_dirs()
    now = time.time()
    for folder in (UPLOAD_ROOT, RESULT_ROOT):
        for path in folder.glob("*"):
            try:
                if now - path.stat().st_mtime <= max_age_seconds:
                    continue
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                continue


def has_upload(upload) -> bool:
    return bool(upload and upload.filename and upload.filename.strip())


def save_upload(upload, directory: Path, fallback_name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(upload.filename or "") or fallback_name
    target = directory / filename
    if target.exists():
        target = directory / f"{target.stem}_{uuid.uuid4().hex[:8]}{target.suffix}"
    upload.save(target)
    return target


def render_home(**context):
    defaults = {
        "error": None,
        "result": None,
        "download_url": None,
        "selected_mode": "nfe",
        "dependency_warnings": dependency_warnings(),
    }
    defaults.update(context)
    return render_template("index.html", **defaults)


@app.get("/")
def index():
    cleanup_old_files()
    return render_home()


@app.post("/")
def process_upload():
    cleanup_old_files()
    ensure_dirs()
    mode = request.form.get("mode", "nfe")
    job_id = uuid.uuid4().hex
    job_dir = UPLOAD_ROOT / job_id
    result_path = RESULT_ROOT / f"{job_id}.xlsx"

    try:
        if mode in ("nfe", "cte"):
            excel_upload = request.files.get("excel_file")
            pdf_upload = request.files.get("pdf_file")
            if not has_upload(excel_upload):
                raise ConferenciaError("Selecione o arquivo Excel SAT.")
            if not has_upload(pdf_upload):
                raise ConferenciaError("Selecione o arquivo PDF.")

            excel_suffix = Path(excel_upload.filename).suffix.lower()
            pdf_suffix = Path(pdf_upload.filename).suffix.lower()
            if excel_suffix not in (".xlsx", ".xlsm", ".xls"):
                raise ConferenciaError("O arquivo SAT precisa ser .xlsx, .xlsm ou .xls.")
            if pdf_suffix != ".pdf":
                raise ConferenciaError("O Registro de Entradas precisa ser PDF.")

            excel_path = save_upload(excel_upload, job_dir, f"sat{excel_suffix}")
            pdf_path = save_upload(pdf_upload, job_dir, "registro.pdf")
            result = processar_documento(mode, str(excel_path), str(pdf_path))
            raw = result.pop("raw")
            exportar_documento(raw["matched"], raw["so_excel"], raw["so_pdf"], raw["modo"], result_path)
            return render_home(
                result=result,
                download_url=url_for("download_result", job_id=job_id),
                selected_mode=mode,
            )

        if mode == "teste":
            teste_upload = request.files.get("teste_file")
            rpt_upload = request.files.get("rpt_file")
            if not has_upload(teste_upload):
                raise ConferenciaError("Selecione o arquivo Teste.")
            if not has_upload(rpt_upload):
                raise ConferenciaError("Selecione o arquivo RPT.")

            allowed = (".xlsx", ".xlsm", ".xls", ".csv")
            teste_suffix = Path(teste_upload.filename).suffix.lower()
            rpt_suffix = Path(rpt_upload.filename).suffix.lower()
            if teste_suffix not in allowed or rpt_suffix not in allowed:
                raise ConferenciaError("Teste e RPT precisam ser .xls, .xlsx, .xlsm ou .csv.")

            teste_path = save_upload(teste_upload, job_dir, f"teste{teste_suffix}")
            rpt_path = save_upload(rpt_upload, job_dir, f"rpt{rpt_suffix}")
            result = processar_teste(str(teste_path), str(rpt_path))
            raw = result.pop("raw")
            exportar_teste(raw["batidos"], raw["so_teste"], raw["so_rpt"], raw["divergentes"], result_path)
            return render_home(
                result=result,
                download_url=url_for("download_result", job_id=job_id),
                selected_mode=mode,
            )

        raise ConferenciaError("Modo invalido.")
    except Exception as exc:
        result_path.unlink(missing_ok=True)
        return render_home(error=str(exc), selected_mode=mode), 400
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.get("/download/<job_id>")
def download_result(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404)
    result_path = RESULT_ROOT / f"{job_id}.xlsx"
    if not result_path.is_file():
        abort(404)
    return send_file(
        result_path,
        as_attachment=True,
        download_name=f"conferencia_fiscal_{job_id[:8]}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.errorhandler(413)
def upload_too_large(_error):
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return render_home(error=f"Upload maior que o limite de {limit_mb} MB."), 413


if __name__ == "__main__":
    ensure_dirs()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5002"))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host=host, port=port, debug=debug)
