import importlib
import logging
import os
import secrets
import sqlite3
import time
import urllib.request
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.utils import secure_filename

from ai.ollama import perguntar_ia
from auth import (admin_required, login_required, recepcao_required,
                  superadmin_required, usuario_atual)
from database.models import agenda as agenda_model
from database.models import chamados_ti as chamados_model
from database.models import estoque_ti as estoque_model
from database.models import hub_apps as hub_model
from database.models import noticias as noticias_model
from database.models import pops as pops_model
from database.models import usuarios as usuarios_model

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "enterprise_intranet_2026")

DB_PATH = "database/intranet.db"
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
_fh = RotatingFileHandler(os.path.join(LOG_DIR,"app.log"), maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(_fmt)
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])

CATEGORIAS_POP = ["Fiscal","RH","Administrativo","TI","Operacional","Segurança","Qualidade","Comercial","Outros"]
ROTAS_PUBLICAS = {"login", "static"}
_PAIS_IP_CACHE = {}

# ── TABELAS ────────────────────────────────────────────────
def criar_tabelas():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS acessos(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, hostname TEXT,
        pagina TEXT, navegador TEXT, pais TEXT,
        data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("PRAGMA table_info(acessos)")
    colunas_acessos = {linha[1] for linha in c.fetchall()}
    if "pais" not in colunas_acessos:
        c.execute("ALTER TABLE acessos ADD COLUMN pais TEXT")

    c.execute("""CREATE TABLE IF NOT EXISTS salas(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE,
        capacidade INTEGER DEFAULT 0, descricao TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS reservas(
        id INTEGER PRIMARY KEY AUTOINCREMENT, sala_id INTEGER NOT NULL,
        titulo TEXT NOT NULL, responsavel TEXT NOT NULL,
        data_reserva DATE NOT NULL, hora_inicio TIME NOT NULL, hora_fim TIME NOT NULL,
        observacao TEXT, criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sala_id) REFERENCES salas(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS usuarios(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, senha_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'comum', setor TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS noticias(
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
        resumo TEXT, conteudo TEXT, autor TEXT,
        caminho_anexo TEXT, nome_anexo TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS eventos_agenda(
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
        descricao TEXT, data_evento DATE NOT NULL,
        hora_inicio TIME, hora_fim TIME,
        sala TEXT NOT NULL DEFAULT 'Geral',
        criado_por TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS pops(
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
        categoria TEXT DEFAULT 'Geral', nome_arquivo TEXT NOT NULL,
        caminho_arquivo TEXT NOT NULL, conteudo_texto TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS hub_apps(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
        descricao TEXT, icone TEXT DEFAULT 'fa-solid fa-mobile-screen',
        url TEXT NOT NULL, setor TEXT NOT NULL DEFAULT 'Geral',
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS chamados_ti(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        usuario_nome TEXT NOT NULL,
        titulo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        prioridade TEXT DEFAULT 'normal',
        status TEXT NOT NULL DEFAULT 'aberto',
        responsavel TEXT,
        resposta TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        respondido_em DATETIME,
        resolvido_em DATETIME,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS estoque_ti(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        categoria TEXT NOT NULL DEFAULT 'Perifericos',
        quantidade INTEGER NOT NULL DEFAULT 0,
        localizacao TEXT,
        observacao TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    # Seeds
    c.execute("SELECT COUNT(*) FROM salas")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO salas(nome,capacidade) VALUES(?,?)",[
            ("Sala Reunião 01",8),("Sala Reunião 02",8),
            ("Sala Diretoria",12),("Sala Treinamento",30)])

    c.execute("SELECT COUNT(*) FROM hub_apps")
    if c.fetchone()[0] == 0:
        apps_seed = [
            ("Dashboard Fiscal","Indicadores e conferências fiscais (SAT, CT-e, NF-e).",
             "fa-solid fa-file-invoice-dollar","/apps/fiscal/dashboard","Fiscal"),
            ("Reserva de Salas","Agende salas de reunião da empresa.",
             "fa-solid fa-calendar-days","/reservas","Administrativo"),
            ("Gerador de RPA","Cria scripts de automação a partir de uma lista de passos.",
             "fa-solid fa-robot","/apps/gerador_rpa/","Automações"),
            ("Treinamentos","Trilhas de treinamento e capacitação dos colaboradores.",
             "fa-solid fa-graduation-cap","/apps/rh/treinamentos","RH"),
            ("Gerador RPA - Autônomos","Gera TXT de importação de autônomos a partir da planilha de contratos.",
             "fa-solid fa-file-export","/apps/autonomo_rpa/","Automações"),
        ]
        c.executemany(
            "INSERT INTO hub_apps(nome,descricao,icone,url,setor) VALUES(?,?,?,?,?)",
            apps_seed)

    conn.commit()
    conn.close()

# ── BOOTSTRAP SUPERADMIN ───────────────────────────────────
def bootstrap_superadmin():
    if usuarios_model.contar_usuarios() > 0:
        return
    senha = secrets.token_urlsafe(9)
    usuarios_model.criar_usuario("Administrador","admin@enterprise.local",senha,"superadmin","TI")
    mensagem = f"Superadmin criado -> admin@enterprise.local | Senha tempor\u00e1ria: {senha}"
    logging.warning(mensagem)
    try:
        with open(os.path.join(LOG_DIR, "app.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | WARNING | {mensagem}\n")
    except Exception:
        pass

# ── CARREGAR BLUEPRINTS ───────────────────────────────────
def carregar_apps():
    apps_dir = Path("apps")
    if not apps_dir.exists():
        return
    for pasta in apps_dir.iterdir():
        if not pasta.is_dir() or pasta.name.startswith("__"):
            continue
        try:
            modulo = importlib.import_module(f"apps.{pasta.name}")
            if hasattr(modulo, "bp"):
                app.register_blueprint(modulo.bp)
                logging.info(f"Blueprint: {pasta.name}")
        except Exception as e:
            logging.error(f"Erro carregando {pasta.name}: {e}")

# ── BEFORE REQUEST ────────────────────────────────────────
def _obter_ip():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or ""
    return ip.split(",")[0].strip() or "desconhecido"

def _pais_do_ip(ip):
    if not ip or ip in ("desconhecido", "127.0.0.1", "::1", "localhost"):
        return "Local"
    if ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")):
        return "Rede local"
    if ip in _PAIS_IP_CACHE:
        return _PAIS_IP_CACHE[ip]
    pais = "N/A"
    try:
        with urllib.request.urlopen(f"https://ipapi.co/{ip}/country_name/", timeout=1.5) as resp:
            texto = resp.read().decode("utf-8", errors="ignore").strip()
            if texto and "error" not in texto.lower():
                pais = texto[:80]
    except Exception:
        pass
    _PAIS_IP_CACHE[ip] = pais
    return pais

def _log_login(tipo, email):
    ip = _obter_ip()
    linha = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {tipo} | {email} | {ip} | {_pais_do_ip(ip)}\n"
    try:
        with open(os.path.join(LOG_DIR,"logins.txt"),"a",encoding="utf-8") as f:
            f.write(linha)
    except Exception as e:
        logging.error(f"Erro logins.txt: {e}")

import socket as _socket

@app.before_request
def registrar_acesso():
    try:
        ip = _obter_ip()
        try: hostname = _socket.gethostbyaddr(ip)[0]
        except: hostname = "N/A"
        pais = _pais_do_ip(ip)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO acessos(ip,hostname,pagina,navegador,pais) VALUES(?,?,?,?,?)",
                     (ip, hostname, request.path, request.headers.get("User-Agent",""), pais))
        conn.commit(); conn.close()
    except Exception as e:
        logging.error(f"Erro acesso: {e}")

@app.before_request
def exigir_login():
    ep = request.endpoint
    if not ep or ep in ROTAS_PUBLICAS or ep.startswith("static"):
        return
    if not session.get("usuario_id"):
        if request.path.startswith("/api/"):
            return jsonify(erro="Não autenticado."), 401
        return redirect(url_for("login", proximo=request.path))

@app.context_processor
def injetar_usuario():
    return dict(usuario_logado=usuario_atual())

# ══════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════

# ── AUTH ──────────────────────────────────────────────────
@app.route("/login", methods=["GET","POST"])
def login():
    if session.get("usuario_id"):
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email","").strip()
        senha = request.form.get("senha","")
        u = usuarios_model.buscar_usuario_por_email(email)
        if not u or not u["ativo"] or not usuarios_model.verificar_senha(u, senha):
            _log_login("FALHA", email)
            flash("E-mail ou senha inválidos.", "erro")
            return redirect(url_for("login"))
        _log_login("SUCESSO", email)
        session["usuario_id"] = u["id"]
        return redirect(request.args.get("proximo") or url_for("home"))
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    u = usuario_atual()
    if u: _log_login("LOGOUT", u["email"])
    session.clear()
    flash("Você saiu.", "sucesso")
    return redirect(url_for("login"))

# ── HOME ──────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html",
        total_apps=hub_model.contar_apps(),
        total_pops=pops_model.contar_pops(),
        total_usuarios=usuarios_model.contar_usuarios(),
        noticias=noticias_model.listar_noticias(limite=5),
        pops_recentes=pops_model.listar_pops()[:6],
        apps_hub=hub_model.listar_apps(apenas_ativos=True)[:6]
    )

# ── NOTÍCIAS ─────────────────────────────────────────────
@app.route("/noticias")
def noticias():
    return render_template("noticias.html", noticias=noticias_model.listar_noticias())

@app.route("/noticias/<int:nid>")
def noticia_detalhe(nid):
    noticia = noticias_model.buscar_noticia_por_id(nid)
    if not noticia: abort(404)
    return render_template("noticia_detalhe.html", noticia=noticia)

@app.route("/noticias/criar", methods=["POST"])
@admin_required
def noticias_criar():
    titulo   = request.form.get("titulo","").strip()
    resumo   = request.form.get("resumo","").strip()
    conteudo = request.form.get("conteudo","").strip()
    if not titulo:
        flash("Informe o título.", "erro")
        return redirect(url_for("noticias"))

    caminho_anexo = nome_anexo = None
    arquivo = request.files.get("anexo")
    if arquivo and arquivo.filename:
        pasta = Path("static/uploads/noticias")
        pasta.mkdir(parents=True, exist_ok=True)
        nome_seg = f"{int(time.time())}_{secure_filename(arquivo.filename)}"
        caminho = pasta / nome_seg
        arquivo.save(caminho)
        caminho_anexo = str(caminho)
        nome_anexo    = arquivo.filename

    u = usuario_atual()
    noticias_model.criar_noticia(titulo, resumo, conteudo, u["nome"] if u else "Admin",
                                  caminho_anexo, nome_anexo)
    flash("Notícia publicada!", "sucesso")
    return redirect(url_for("noticias"))

@app.route("/noticias/<int:nid>/anexo")
def noticias_anexo(nid):
    n = noticias_model.buscar_noticia_por_id(nid)
    if not n or not n["caminho_anexo"]: abort(404)
    return send_file(n["caminho_anexo"], as_attachment=True, download_name=n["nome_anexo"])

@app.route("/noticias/<int:nid>/excluir", methods=["POST"])
@admin_required
def noticias_excluir(nid):
    noticias_model.excluir_noticia(nid)
    flash("Notícia removida.", "sucesso")
    return redirect(url_for("noticias"))

# ── AGENDA ──────────────────────────────────────────────
@app.route("/agenda")
def agenda():
    hoje = date.today()
    ano  = request.args.get("ano",  type=int) or hoje.year
    mes  = request.args.get("mes",  type=int) or hoje.month
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    salas = [r["nome"] for r in conn.execute("SELECT nome FROM salas ORDER BY nome").fetchall()]
    eventos_proximos = conn.execute(
        """
        SELECT * FROM eventos_agenda
        WHERE date(data_evento) >= date('now')
        ORDER BY sala, data_evento, hora_inicio
        LIMIT 60
        """
    ).fetchall()
    conn.close()
    eventos_por_sala = {}
    for evento in eventos_proximos:
        eventos_por_sala.setdefault(evento["sala"], []).append(evento)
    return render_template("agenda.html", ano=ano, mes=mes, salas=salas, eventos_por_sala=eventos_por_sala)

@app.route("/api/agenda/eventos")
def api_agenda_eventos():
    ano = request.args.get("ano", type=int)
    mes = request.args.get("mes", type=int)
    if not ano or not mes:
        return jsonify(erro="Parâmetros obrigatórios."), 400
    eventos = agenda_model.listar_eventos_mes(ano, mes)
    dados = [{
        "id": e["id"], "titulo": e["titulo"], "descricao": e["descricao"],
        "data": e["data_evento"], "hora_inicio": e["hora_inicio"],
        "hora_fim": e["hora_fim"], "sala": e["sala"],
        "cor": agenda_model.cor_da_sala(e["sala"]),
        "criado_por": e["criado_por"],
    } for e in eventos]
    return jsonify(eventos=dados)

@app.route("/agenda/criar", methods=["POST"])
@recepcao_required
def agenda_criar():
    titulo      = request.form.get("titulo","").strip()
    descricao   = request.form.get("descricao","").strip()
    data_evento = request.form.get("data","").strip()
    hora_inicio = request.form.get("hora_inicio","").strip() or None
    hora_fim    = request.form.get("hora_fim","").strip() or None
    sala        = request.form.get("sala","").strip() or "Geral"
    if not titulo or not data_evento:
        flash("Informe título e data.", "erro")
        return redirect(url_for("agenda"))
    u = usuario_atual()
    agenda_model.criar_evento(titulo, descricao, data_evento, hora_inicio, hora_fim, sala,
                               u["nome"] if u else "Sistema")
    flash("Evento adicionado.", "sucesso")
    ano, mes, _ = data_evento.split("-")
    return redirect(url_for("agenda", ano=int(ano), mes=int(mes)))

@app.route("/agenda/<int:eid>/editar", methods=["POST"])
@recepcao_required
def agenda_editar(eid):
    titulo      = request.form.get("titulo","").strip()
    descricao   = request.form.get("descricao","").strip()
    data_evento = request.form.get("data","").strip()
    hora_inicio = request.form.get("hora_inicio","").strip() or None
    hora_fim    = request.form.get("hora_fim","").strip() or None
    sala        = request.form.get("sala","").strip() or "Geral"
    agenda_model.atualizar_evento(eid, titulo, descricao, data_evento, hora_inicio, hora_fim, sala)
    flash("Evento atualizado.", "sucesso")
    ano, mes, _ = data_evento.split("-")
    return redirect(url_for("agenda", ano=int(ano), mes=int(mes)))

@app.route("/agenda/<int:eid>/excluir", methods=["POST"])
@recepcao_required
def agenda_excluir(eid):
    agenda_model.excluir_evento(eid)
    flash("Evento removido.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/api/agenda/evento/<int:eid>")
def api_agenda_evento(eid):
    e = agenda_model.buscar_evento_por_id(eid)
    if not e: return jsonify(erro="Não encontrado."), 404
    return jsonify(dict(e))

# ── RESERVAS ─────────────────────────────────────────────
@app.route("/reservas", methods=["GET","POST"])
def reservas():
    if request.method == "GET":
        return redirect(url_for("agenda"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == "POST":
        sala_nome   = request.form.get("sala","").strip()
        titulo      = request.form.get("titulo","").strip()
        data_r      = request.form.get("data","").strip()
        hi          = request.form.get("hora_inicio","").strip()
        hf          = request.form.get("hora_fim","").strip()
        responsavel = request.form.get("responsavel","").strip()
        obs         = request.form.get("observacao","").strip()

        if not all([sala_nome, titulo, data_r, hi, hf, responsavel]):
            flash("Preencha todos os campos obrigatórios.", "erro")
            conn.close(); return redirect(url_for("agenda"))
        if hf <= hi:
            flash("Hora final deve ser depois da inicial.", "erro")
            conn.close(); return redirect(url_for("agenda"))

        cursor.execute("SELECT id FROM salas WHERE nome=?", (sala_nome,))
        sala = cursor.fetchone()
        sala_id = sala["id"] if sala else cursor.execute("INSERT INTO salas(nome) VALUES(?)",(sala_nome,)).lastrowid
        conn.commit()

        cursor.execute(
            "SELECT id FROM reservas WHERE sala_id=? AND data_reserva=? AND NOT(hora_fim<=? OR hora_inicio>=?)",
            (sala_id, data_r, hi, hf))
        if cursor.fetchone():
            flash("Já existe reserva nesse horário.", "erro")
            conn.close(); return redirect(url_for("agenda"))

        cursor.execute(
            "INSERT INTO reservas(sala_id,titulo,responsavel,data_reserva,hora_inicio,hora_fim,observacao) VALUES(?,?,?,?,?,?,?)",
            (sala_id, titulo, responsavel, data_r, hi, hf, obs))
        conn.commit()

        # Sincroniza com a agenda automaticamente
        descricao_evento = f"Reserva por {responsavel}" + (f" — {obs}" if obs else "")
        agenda_model.criar_evento(titulo, descricao_evento, data_r, hi, hf, sala_nome, responsavel)

        flash("Reserva criada e adicionada à agenda!", "sucesso")
        conn.close(); return redirect(url_for("agenda"))

    cursor.execute("SELECT nome FROM salas ORDER BY nome")
    salas = [r["nome"] for r in cursor.fetchall()]
    cursor.execute("""SELECT reservas.*,salas.nome AS sala_nome FROM reservas
        JOIN salas ON salas.id=reservas.sala_id
        WHERE date(data_reserva)>=date('now')
        ORDER BY data_reserva,hora_inicio LIMIT 30""")
    lista = cursor.fetchall()
    conn.close()
    return render_template("reservas.html", reservas=lista, salas=salas)

@app.route("/reservas/<int:rid>/excluir", methods=["POST"])
@admin_required
def reservas_excluir(rid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM reservas WHERE id=?", (rid,))
    conn.commit(); conn.close()
    flash("Reserva excluída.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/reservas/<int:rid>/editar", methods=["POST"])
@admin_required
def reservas_editar(rid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    titulo   = request.form.get("titulo","").strip()
    data_r   = request.form.get("data","").strip()
    hi       = request.form.get("hora_inicio","").strip()
    hf       = request.form.get("hora_fim","").strip()
    resp     = request.form.get("responsavel","").strip()
    obs      = request.form.get("observacao","").strip()
    cursor.execute(
        "UPDATE reservas SET titulo=?,responsavel=?,data_reserva=?,hora_inicio=?,hora_fim=?,observacao=? WHERE id=?",
        (titulo, resp, data_r, hi, hf, obs, rid))
    conn.commit(); conn.close()
    flash("Reserva atualizada.", "sucesso")
    return redirect(url_for("agenda"))

# ── POPS ─────────────────────────────────────────────────
@app.route("/pops")
def pops():
    busca     = request.args.get("q","").strip()
    categoria = request.args.get("cat","").strip()
    lista     = pops_model.listar_pops(busca=busca, categoria=categoria or None)
    return render_template("pops.html", pops=lista, busca=busca,
                           categoria=categoria, categorias=CATEGORIAS_POP)

@app.route("/pops/upload", methods=["POST"])
@admin_required
def pops_upload():
    arquivo   = request.files.get("arquivo")
    titulo    = request.form.get("titulo","").strip()
    categoria = request.form.get("categoria","Outros").strip()
    if categoria not in CATEGORIAS_POP:
        categoria = "Outros"
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo.", "erro"); return redirect(url_for("pops"))
    ext = Path(arquivo.filename).suffix.lower()
    if ext not in (".pdf",".docx",".txt"):
        flash("Formatos aceitos: PDF, DOCX, TXT.", "erro"); return redirect(url_for("pops"))
    if not titulo:
        titulo = Path(arquivo.filename).stem
    pasta = Path("static/uploads/pops")
    pasta.mkdir(parents=True, exist_ok=True)
    nome_seg = f"{int(time.time())}_{secure_filename(arquivo.filename)}"
    caminho  = pasta / nome_seg
    arquivo.save(caminho)
    texto = pops_model.extrair_texto(caminho, ext)
    pops_model.criar_pop(titulo, categoria, arquivo.filename, str(caminho), texto)
    flash("POP enviado!", "sucesso")
    return redirect(url_for("pops"))

@app.route("/pops/<int:pid>/download")
def pops_download(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if not p: abort(404)
    return send_file(p["caminho_arquivo"], as_attachment=True, download_name=p["nome_arquivo"])

@app.route("/pops/<int:pid>/visualizar")
def pops_visualizar(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if not p: abort(404)
    ext = Path(p["nome_arquivo"]).suffix.lower()
    if ext == ".pdf":
        return send_file(p["caminho_arquivo"], mimetype="application/pdf")
    # TXT / DOCX → mostra o texto extraído
    return render_template("pop_visualizar.html", pop=p)

@app.route("/pops/<int:pid>/excluir", methods=["POST"])
@admin_required
def pops_excluir(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if p:
        try: os.remove(p["caminho_arquivo"])
        except OSError: pass
        pops_model.excluir_pop(pid)
        flash("POP removido.", "sucesso")
    return redirect(url_for("pops"))

# ── HUB DE APPS ──────────────────────────────────────────
@app.route("/apps")
def hub_apps():
    por_setor = hub_model.listar_apps_por_setor()
    setores   = sorted(por_setor.keys())
    return render_template("hub_apps.html", por_setor=por_setor, setores=setores)

# ── CHAMADOS E ESTOQUE DE TI ───────────────────────────────
@app.route("/ti/chamados", methods=["GET","POST"])
def chamados_ti():
    u = usuario_atual()
    if request.method == "POST":
        titulo = request.form.get("titulo","").strip()
        descricao = request.form.get("descricao","").strip()
        prioridade = request.form.get("prioridade","normal").strip()
        if not titulo or not descricao:
            flash("Informe titulo e descricao do chamado.", "erro")
            return redirect(url_for("chamados_ti"))
        chamados_model.criar_chamado(u["id"], u["nome"], titulo, descricao, prioridade)
        flash("Chamado registrado. O TI vai acompanhar pela fila.", "sucesso")
        return redirect(url_for("chamados_ti"))

    admin_ti = u and u["role"] in ("admin", "superadmin")
    chamados = chamados_model.listar_chamados(u["id"], admin=admin_ti)
    return render_template(
        "chamados_ti.html",
        chamados=chamados,
        responsaveis=chamados_model.RESPONSAVEIS_TI,
        status_opcoes=chamados_model.STATUS_CHAMADO,
        admin_ti=admin_ti,
        tempo_resposta=chamados_model.tempo_resposta,
        tempo_resolucao=chamados_model.tempo_resolucao,
    )

@app.route("/ti/chamados/<int:chamado_id>/atualizar", methods=["POST"])
@admin_required
def chamados_ti_atualizar(chamado_id):
    responsavel = request.form.get("responsavel","").strip()
    resposta = request.form.get("resposta","").strip()
    status = request.form.get("status","em_atendimento").strip()
    try:
        ok = chamados_model.atualizar_atendimento(chamado_id, responsavel, resposta, status)
    except ValueError:
        ok = False
    flash("Chamado atualizado." if ok else "Nao foi possivel atualizar o chamado.", "sucesso" if ok else "erro")
    return redirect(url_for("chamados_ti"))

@app.route("/ti/chamados/<int:chamado_id>/excluir", methods=["POST"])
@admin_required
def chamados_ti_excluir(chamado_id):
    chamados_model.excluir_chamado(chamado_id)
    flash("Chamado removido.", "sucesso")
    return redirect(url_for("chamados_ti"))

@app.route("/ti/estoque", methods=["GET","POST"])
@admin_required
def estoque_ti():
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "criar":
            nome = request.form.get("nome","").strip()
            categoria = request.form.get("categoria","Perifericos").strip()
            quantidade = request.form.get("quantidade", type=int) or 0
            localizacao = request.form.get("localizacao","").strip()
            observacao = request.form.get("observacao","").strip()
            if not nome:
                flash("Informe o nome do item.", "erro")
            else:
                estoque_model.criar_item(nome, categoria, quantidade, localizacao, observacao)
                flash("Item adicionado ao estoque.", "sucesso")
        elif acao == "atualizar":
            estoque_model.atualizar_item(
                request.form.get("item_id", type=int),
                request.form.get("nome",""),
                request.form.get("categoria","Perifericos"),
                request.form.get("quantidade", type=int) or 0,
                request.form.get("localizacao",""),
                request.form.get("observacao",""),
            )
            flash("Item atualizado.", "sucesso")
        elif acao == "excluir":
            estoque_model.excluir_item(request.form.get("item_id", type=int))
            flash("Item removido.", "sucesso")
        return redirect(url_for("estoque_ti"))

    return render_template("estoque_ti.html", itens=estoque_model.listar_itens())

# ── ADMIN APPS (cadastrar/remover cards do hub) ─────────
@app.route("/admin/apps", methods=["GET","POST"])
@admin_required
def admin_apps():
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "criar":
            hub_model.criar_app(
                request.form.get("nome",""),
                request.form.get("descricao",""),
                request.form.get("icone","fa-solid fa-mobile-screen"),
                request.form.get("url",""),
                request.form.get("setor","Geral"),
            )
            flash("App cadastrado.", "sucesso")
        elif acao == "excluir":
            hub_model.excluir_app(request.form.get("app_id", type=int))
            flash("App removido.", "sucesso")
        elif acao == "toggle":
            hub_model.alternar_ativo(request.form.get("app_id", type=int))
            flash("Status alterado.", "sucesso")
        return redirect(url_for("admin_apps"))

    todos = hub_model.listar_apps(apenas_ativos=False)
    return render_template("admin_apps.html", apps=todos,
                           setores_conhecidos=["Fiscal","RH","Administrativo","TI","Automações","Comercial","Geral"])

# ── IA ────────────────────────────────────────────────────
@app.route("/ia")
def ia():
    return render_template("ia.html")

@app.route("/api/ia", methods=["POST"])
def api_ia():
    dados    = request.get_json(silent=True) or {}
    pergunta = (dados.get("pergunta") or "").strip()
    if not pergunta:
        return jsonify(sucesso=False, erro="Pergunta vazia."), 400
    pops_rel     = pops_model.buscar_pops_relevantes(pergunta)
    noticias_rel = noticias_model.buscar_noticias_relevantes(pergunta)
    eventos_rel  = agenda_model.buscar_eventos_relevantes(pergunta)
    try:
        resposta = perguntar_ia(pergunta, pops_rel, noticias_rel, eventos_rel)
        fontes   = (
            [f"POP: {p['titulo']}" for p in pops_rel]
            + [f"Notícia: {n['titulo']}" for n in noticias_rel]
            + [f"Agenda: {e['titulo']}" for e in eventos_rel]
        )
        return jsonify(sucesso=True, resposta=resposta, fontes=fontes)
    except Exception as e:
        logging.error(f"IA erro: {e}")
        return jsonify(sucesso=False, erro="Servidor Ollama indisponível."), 500

# ── ACESSOS ──────────────────────────────────────────────
@app.route("/admin/acessos")
@admin_required
def admin_acessos():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    acessos = conn.execute("SELECT * FROM acessos ORDER BY id DESC LIMIT 500").fetchall()
    conn.close()
    logins = []
    p = os.path.join(LOG_DIR,"logins.txt")
    if os.path.exists(p):
        linhas = [l.strip() for l in open(p,encoding="utf-8") if l.strip()]
        logins = list(reversed(linhas[-200:]))
    return render_template("admin_acessos.html", acessos=acessos, logins=logins)

# ── USUÁRIOS ─────────────────────────────────────────────
@app.route("/admin/usuarios", methods=["GET","POST"])
@superadmin_required
def admin_usuarios():
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "criar":
            nome  = request.form.get("nome","").strip()
            email = request.form.get("email","").strip()
            senha = request.form.get("senha","")
            role  = request.form.get("role","comum")
            setor = request.form.get("setor","").strip()
            if not nome or not email or not senha:
                flash("Preencha nome, e-mail e senha.", "erro")
            elif usuarios_model.buscar_usuario_por_email(email):
                flash("E-mail já cadastrado.", "erro")
            else:
                usuarios_model.criar_usuario(nome, email, senha, role, setor)
                flash("Usuário criado.", "sucesso")
        elif acao == "atualizar_role":
            usuarios_model.atualizar_role(request.form.get("usuario_id",type=int), request.form.get("role"))
            flash("Papel atualizado.", "sucesso")
        elif acao == "alternar_status":
            usuarios_model.atualizar_status(request.form.get("usuario_id",type=int),
                                             request.form.get("ativo")=="1")
            flash("Status atualizado.", "sucesso")
        elif acao == "excluir":
            uid = request.form.get("usuario_id", type=int)
            atual = usuario_atual()
            if atual and uid == atual["id"]:
                flash("Voce nao pode excluir o proprio usuario logado.", "erro")
            else:
                usuarios_model.excluir_usuario(uid)
                flash("Usuario removido.", "sucesso")
        return redirect(url_for("admin_usuarios"))
    return render_template("admin_usuarios.html",
                           usuarios=usuarios_model.listar_usuarios(),
                           papeis=usuarios_model.PAPEIS)

# ── ERROS ────────────────────────────────────────────────
@app.errorhandler(404)
def e404(e): return render_template("erros/404.html"), 404
@app.errorhandler(500)
def e500(e): return render_template("erros/500.html"), 500

# ── STARTUP ──────────────────────────────────────────────
criar_tabelas()
bootstrap_superadmin()
carregar_apps()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
