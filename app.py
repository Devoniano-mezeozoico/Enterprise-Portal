import importlib
import logging
import os
import secrets
import sqlite3
import time
import urllib.request
from urllib.parse import urlparse
from datetime import date, datetime
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

from ai.ollama import perguntar_ia
from auth import (admin_required, login_required, recepcao_required,
                  superadmin_required, usuario_atual)
from config import AppConfig
from database.migrations import aplicar_migracoes
from database.models import agenda as agenda_model
from database.models import atendimentos as atendimentos_model
from database.models import auditoria as auditoria_model
from database.models import chamados_ti as chamados_model
from database.models import chat as chat_model
from database.models import comunicados as comunicados_model
from database.models import estoque_ti as estoque_model
from database.models import hub_apps as hub_model
from database.models import honeypot_fake as honeypot_fake_model
from database.models import noticias as noticias_model
from database.models import pops as pops_model
from database.models import salas as salas_model
from database.models import usuarios as usuarios_model
from database.models import unidades as unidades_model
from security import install_security

app = Flask(__name__)
app.config.from_object(AppConfig)
install_security(app)
if app.config.get("SECRET_KEY_IS_TEMPORARY"):
    logging.warning(
        "SECRET_KEY nao definida. Usando chave temporaria de desenvolvimento; "
        "defina SECRET_KEY antes de publicar."
    )

DB_PATH = app.config["DB_PATH"]
LOG_DIR = app.config["LOG_DIR"]
DEFAULT_ADMIN_EMAIL = app.config["DEFAULT_ADMIN_EMAIL"]
os.makedirs(LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
_fh = RotatingFileHandler(os.path.join(LOG_DIR,"app.log"), maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(_fmt)
_ch = logging.StreamHandler()
_ch.setFormatter(_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_fh, _ch])

CATEGORIAS_POP = ["Fiscal","RH","Administrativo","TI","Operacional","Segurança","Qualidade","Comercial","Outros"]
ROTAS_PUBLICAS = {"login", "static", "admin_painel", "portal_notifications_sw"}
_PAIS_IP_CACHE = {}
EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
ROTAS_ABAS = (
    ("/noticias", "noticias"),
    ("/apps", "apps"),
    ("/agenda", "agenda"),
    ("/reservas", "agenda"),
    ("/chat", "chat"),
    ("/api/chat", "chat"),
    ("/pops", "pops"),
    ("/ti/chamados", "chamados_ti"),
    ("/ia", "ia"),
    ("/api/ia", "ia"),
)


def _row_get(row, campo, padrao=""):
    if not row:
        return padrao
    if isinstance(row, dict):
        return row.get(campo, padrao)
    try:
        return row[campo]
    except (KeyError, IndexError, TypeError):
        return padrao


def _destino_interno(destino, fallback_endpoint="home"):
    destino = (destino or "").strip()
    if not destino:
        return url_for(fallback_endpoint)
    parsed = urlparse(destino)
    if parsed.netloc:
        if parsed.netloc != request.host:
            return url_for(fallback_endpoint)
        destino = parsed.path or "/"
        if parsed.query:
            destino += f"?{parsed.query}"
        parsed = urlparse(destino)
    if parsed.scheme or not destino.startswith("/") or destino.startswith("//"):
        return url_for(fallback_endpoint)
    return destino

def _categorias_pop_disponiveis():
    categorias = set(CATEGORIAS_POP)
    try:
        categorias.update(c for c in pops_model.listar_categorias() if c)
    except Exception:
        pass
    return sorted(categorias)

def _resolver_arquivo_pop(pop):
    if not pop:
        return None
    candidatos = []
    caminho_salvo = pop["caminho_arquivo"] if "caminho_arquivo" in pop.keys() else ""
    nome_arquivo = pop["nome_arquivo"] if "nome_arquivo" in pop.keys() else ""
    if caminho_salvo:
        candidatos.append(Path(caminho_salvo))
        candidatos.append(Path.cwd() / caminho_salvo)
    pasta = Path("static/uploads/pops")
    if nome_arquivo:
        candidatos.append(pasta / nome_arquivo)
        candidatos.extend(pasta.glob(f"*_{nome_arquivo}"))
    for candidato in candidatos:
        try:
            if candidato and candidato.exists() and candidato.is_file():
                return candidato
        except OSError:
            continue
    return None


def _noticia_eh_imagem(noticia):
    nome = _row_get(noticia, "nome_anexo") or _row_get(noticia, "caminho_anexo")
    return Path(nome or "").suffix.lower() in EXTENSOES_IMAGEM


def _resolver_arquivo_noticia(noticia):
    if not noticia:
        return None

    caminho_salvo = _row_get(noticia, "caminho_anexo")
    nome_anexo = _row_get(noticia, "nome_anexo")
    candidatos = []

    if caminho_salvo:
        caminho = Path(caminho_salvo)
        candidatos.append(caminho)
        if not caminho.is_absolute():
            candidatos.append(Path.cwd() / caminho)

    pasta = Path("static/uploads/noticias")
    nomes = [nome for nome in {nome_anexo, secure_filename(nome_anexo or "")} if nome]
    for nome in nomes:
        candidatos.append(pasta / nome)

    for candidato in candidatos:
        try:
            if candidato and candidato.exists() and candidato.is_file():
                return candidato
        except OSError:
            continue

    if pasta.exists() and nomes:
        nomes_lower = [nome.lower() for nome in nomes]
        for arquivo in pasta.iterdir():
            if not arquivo.is_file():
                continue
            nome_arquivo = arquivo.name.lower()
            if any(nome_arquivo == nome or nome_arquivo.endswith(f"_{nome}") for nome in nomes_lower):
                return arquivo

    return None

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
        tipo TEXT NOT NULL DEFAULT 'reserva',
        sala TEXT NOT NULL DEFAULT 'Geral',
        criado_por TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("PRAGMA table_info(eventos_agenda)")
    colunas_eventos = {linha[1] for linha in c.fetchall()}
    if "tipo" not in colunas_eventos:
        c.execute("ALTER TABLE eventos_agenda ADD COLUMN tipo TEXT NOT NULL DEFAULT 'reserva'")

    c.execute("""CREATE TABLE IF NOT EXISTS pops(
        id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
        categoria TEXT DEFAULT 'Geral', nome_arquivo TEXT NOT NULL,
        caminho_arquivo TEXT NOT NULL, conteudo_texto TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS hub_apps(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
        descricao TEXT, icone TEXT DEFAULT 'fa-solid fa-mobile-screen',
        url TEXT NOT NULL, setor TEXT NOT NULL DEFAULT 'Geral',
        setores_liberados TEXT,
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("PRAGMA table_info(hub_apps)")
    colunas_hub_apps = {linha[1] for linha in c.fetchall()}
    if "setores_liberados" not in colunas_hub_apps:
        c.execute("ALTER TABLE hub_apps ADD COLUMN setores_liberados TEXT")

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

    c.execute("""CREATE TABLE IF NOT EXISTS chat_mensagens(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        usuario_nome TEXT NOT NULL,
        mensagem TEXT NOT NULL,
        apagada INTEGER NOT NULL DEFAULT 0,
        apagada_em DATETIME,
        apagada_por_id INTEGER,
        apagada_por_nome TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS atendimento_metricas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        departamento TEXT,
        qtd_atendimentos INTEGER NOT NULL DEFAULT 0,
        tempo_medio_segundos INTEGER NOT NULL DEFAULT 0,
        tempo_medio_formatado TEXT,
        satisfeitos INTEGER NOT NULL DEFAULT 0,
        nao_satisfeitos INTEGER NOT NULL DEFAULT 0,
        total_pesquisa INTEGER NOT NULL DEFAULT 0,
        satisfacao_percentual REAL NOT NULL DEFAULT 0,
        arquivo_origem TEXT,
        tipo_origem TEXT,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("PRAGMA table_info(atendimento_metricas)")
    colunas_atendimentos = {linha[1] for linha in c.fetchall()}
    colunas_novas_atendimentos = {
        "satisfeitos": "INTEGER NOT NULL DEFAULT 0",
        "nao_satisfeitos": "INTEGER NOT NULL DEFAULT 0",
        "total_pesquisa": "INTEGER NOT NULL DEFAULT 0",
        "satisfacao_percentual": "REAL NOT NULL DEFAULT 0",
    }
    for coluna, definicao in colunas_novas_atendimentos.items():
        if coluna not in colunas_atendimentos:
            c.execute(f"ALTER TABLE atendimento_metricas ADD COLUMN {coluna} {definicao}")

    c.execute("""CREATE TABLE IF NOT EXISTS honeypot_tentativas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        pais TEXT,
        rota TEXT,
        caminho_completo TEXT,
        metodo TEXT,
        email_tentado TEXT,
        senha_len INTEGER DEFAULT 0,
        user_agent TEXT,
        referer TEXT,
        nivel TEXT,
        motivo TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS comunicados(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        mensagem TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'informacao',
        exibir_popup INTEGER NOT NULL DEFAULT 1,
        link_url TEXT,
        inicio_em DATETIME,
        fim_em DATETIME,
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_por_id INTEGER,
        criado_por_nome TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        excluido_em DATETIME)""")
    c.execute("PRAGMA table_info(comunicados)")
    colunas_comunicados = {linha[1] for linha in c.fetchall()}
    if "atualizado_em" not in colunas_comunicados:
        c.execute("ALTER TABLE comunicados ADD COLUMN atualizado_em DATETIME")
        c.execute(
            """
            UPDATE comunicados
            SET atualizado_em = COALESCE(atualizado_em, criado_em, CURRENT_TIMESTAMP)
            """
        )
    if "excluido_em" not in colunas_comunicados:
        c.execute("ALTER TABLE comunicados ADD COLUMN excluido_em DATETIME")

    c.execute("""CREATE TABLE IF NOT EXISTS comunicado_leituras(
        comunicado_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        visto_em DATETIME,
        popup_fechado_em DATETIME,
        PRIMARY KEY(comunicado_id, usuario_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS notificacoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL DEFAULT 'informacao',
        titulo TEXT NOT NULL,
        mensagem TEXT,
        url TEXT,
        referencia_tipo TEXT,
        referencia_id INTEGER,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP)""")

    c.execute("""CREATE TABLE IF NOT EXISTS notificacao_leituras(
        notificacao_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        lida_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(notificacao_id, usuario_id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS configuracao_abas(
        chave TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        icone TEXT NOT NULL,
        habilitada_comum INTEGER NOT NULL DEFAULT 1,
        ordem INTEGER NOT NULL DEFAULT 0)""")
    c.executemany(
        """
        INSERT OR IGNORE INTO configuracao_abas(
            chave, nome, endpoint, icone, habilitada_comum, ordem
        ) VALUES(?,?,?,?,1,?)
        """,
        comunicados_model.ABAS_PADRAO,
    )

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
            "INSERT INTO hub_apps(nome,descricao,icone,url,setor,setores_liberados) VALUES(?,?,?,?,?,?)",
            [(nome, desc, icone, url, setor, setor) for nome, desc, icone, url, setor in apps_seed])

    c.execute("SELECT COUNT(*) FROM hub_apps WHERE lower(nome) = lower(?)", ("ADF",))
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO hub_apps(nome,descricao,icone,url,setor,setores_liberados) VALUES(?,?,?,?,?,?)",
            (
                "ADF",
                "Acesso ao sistema ADF.",
                "fa-solid fa-diagram-project",
                os.environ.get("ADF_URL", "").strip() or "/apps/adf",
                "Geral",
                "Todos",
            )
        )

    conn.commit()
    conn.close()

# ── BOOTSTRAP SUPERADMIN ───────────────────────────────────
def bootstrap_superadmin():
    if usuarios_model.contar_usuarios() > 0:
        return
    senha = secrets.token_urlsafe(9)
    usuarios_model.criar_usuario("Administrador", DEFAULT_ADMIN_EMAIL, senha, "superadmin", "TI")
    mensagem = f"Superadmin criado -> {DEFAULT_ADMIN_EMAIL} | Senha tempor\u00e1ria: {senha}"
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


def _snapshot(registro):
    if not registro:
        return None
    if isinstance(registro, dict):
        return dict(registro)
    try:
        return {chave: registro[chave] for chave in registro.keys()}
    except (AttributeError, TypeError):
        return registro


def _auditar(acao, modulo, registro_id=None, anterior=None, novo=None, detalhes=None,
             usuario=None, unidade=None):
    usuario = usuario if usuario is not None else usuario_atual()
    if unidade is None and usuario:
        unidade = unidades_model.unidade_do_usuario(usuario["id"])
    return auditoria_model.registrar_evento(
        usuario=usuario,
        acao=acao,
        modulo=modulo,
        registro_id=registro_id,
        unidade=unidade,
        endereco_ip=_obter_ip(),
        user_agent=request.headers.get("User-Agent", ""),
        anterior=_snapshot(anterior),
        novo=_snapshot(novo),
        detalhes=detalhes,
    )


def _unidade_do_vinculo(vinculo):
    if not vinculo or not vinculo["unidade_id"]:
        return None
    return unidades_model.buscar_unidade(vinculo["unidade_id"])


def _unidade_da_sala(nome_sala):
    sala = salas_model.buscar_sala_por_nome(nome_sala)
    if not sala:
        return None
    return _unidade_do_vinculo(unidades_model.unidade_do_registro("salas", sala["id"]))

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

def _log_chat(acao, usuario, mensagem=None):
    texto = ""
    if mensagem is not None:
        texto = str(mensagem).replace("\r", " ").replace("\n", " ")
    linha = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {acao} | "
        f"id={usuario['id'] if usuario else 'N/A'} | "
        f"nome={usuario['nome'] if usuario else 'N/A'} | mensagem={texto}\n"
    )
    try:
        with open(os.path.join(LOG_DIR, "chat.log"), "a", encoding="utf-8") as f:
            f.write(linha)
    except Exception as e:
        logging.error(f"Erro chat.log: {e}")

def _classificar_honeypot(ip, rota, email_tentado, senha_texto, user_agent, referer, tentativas_ip):
    texto = f"{rota} {email_tentado} {senha_texto} {user_agent} {referer}".lower()
    ferramentas = ("ffuf", "gobuster", "dirsearch", "nikto", "nuclei", "sqlmap", "curl", "wget", "python-requests", "masscan", "zgrab")
    payloads = ("union select", "../", "<script", "sleep(", "benchmark(", "' or", "\" or", "${jndi", ".env", "passwd", "cmd=")
    credenciais_fracas = ("admin", "root", "teste", "test", "123", "senha", "password", "qwerty")

    if any(item in texto for item in ferramentas):
        return "script_kiddie", "User-Agent ou assinatura de ferramenta automatizada."
    if any(item in texto for item in payloads):
        return "senior", "Tentativa com payload de exploracao/injecao."
    if tentativas_ip >= 15:
        return "senior", "Volume alto de tentativas no honeypot."
    if tentativas_ip >= 6:
        return "medio", "Persistencia acima do normal para o mesmo IP."
    if any(item in texto for item in credenciais_fracas):
        return "baixo", "Tentativa com usuario/senha comuns."
    if "mozilla" in (user_agent or "").lower() and not referer and tentativas_ip <= 2:
        return "baixo", "Acesso manual inicial sem referer."
    return "medio", "Tentativa em rota administrativa falsa."


def _registrar_alerta_honeypot(ip, pais, tentativas_ip, nivel, motivo):
    if tentativas_ip not in (5, 10, 15, 20) and tentativas_ip % 25 != 0:
        return
    linha = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ALERTA | "
        f"IP={ip} | PAIS={pais} | TENTATIVAS={tentativas_ip} | NIVEL={nivel} | MOTIVO={motivo}\n"
    )
    try:
        with open(os.path.join(LOG_DIR, "honeypot_alertas.log"), "a", encoding="utf-8") as f:
            f.write(linha)
    except Exception as e:
        logging.error(f"Erro honeypot_alertas.log: {e}")
    logging.warning(linha.strip())


def _log_honeypot_admin_painel(email_tentado="", senha_texto=""):
    ip = _obter_ip()
    pais = _pais_do_ip(ip)
    user_agent = request.headers.get("User-Agent", "")
    referer = request.headers.get("Referer", "")
    caminho_completo = request.full_path if request.query_string else request.path
    senha_len = len(senha_texto or "")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tentativas_ip = conn.execute("SELECT COUNT(*) FROM honeypot_tentativas WHERE ip=?", (ip,)).fetchone()[0] + 1
    nivel, motivo = _classificar_honeypot(ip, request.path, email_tentado, senha_texto, user_agent, referer, tentativas_ip)
    conn.execute(
        """
        INSERT INTO honeypot_tentativas
        (ip, pais, rota, caminho_completo, metodo, email_tentado, senha_len, user_agent, referer, nivel, motivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ip, pais, request.path, caminho_completo, request.method, email_tentado, senha_len, user_agent, referer, nivel, motivo),
    )
    conn.commit()
    conn.close()

    linha = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"IP={ip} | PAIS={pais} | TENTATIVAS_IP={tentativas_ip} | "
        f"NIVEL={nivel} | MOTIVO={motivo} | ROTA={request.path} | "
        f"CAMINHO={caminho_completo} | METODO={request.method} | "
        f"EMAIL={email_tentado or '-'} | SENHA_LEN={senha_len} | "
        f"REFERER={referer or '-'} | USER_AGENT={user_agent}\n"
    )
    try:
        with open(os.path.join(LOG_DIR, "honeypot_admin_painel.log"), "a", encoding="utf-8") as f:
            f.write(linha)
    except Exception as e:
        logging.error(f"Erro honeypot_admin_painel.log: {e}")
    _registrar_alerta_honeypot(ip, pais, tentativas_ip, nivel, motivo)
    return tentativas_ip, nivel, motivo

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
    if request.path.startswith("/admin_painel"):
        return
    if not ep or ep in ROTAS_PUBLICAS or ep.startswith("static"):
        return
    if not session.get("usuario_id"):
        if request.path.startswith("/api/"):
            return jsonify(erro="Não autenticado."), 401
        return redirect(url_for("login", proximo=request.path))
    u = usuario_atual()
    for prefixo, chave_aba in ROTAS_ABAS:
        if request.path == prefixo or request.path.startswith(f"{prefixo}/"):
            if not comunicados_model.usuario_pode_acessar_aba(u, chave_aba):
                if request.path.startswith("/api/"):
                    return jsonify(erro="Este recurso foi desabilitado pela gestão."), 403
                flash("Esta área está temporariamente indisponível para usuários comuns.", "erro")
                return redirect(url_for("home"))
            break

def _branding_context():
    empresa = app.config["COMPANY_NAME"]
    inicial = (empresa.strip()[:1] or "P").upper()
    return {
        "app_name": app.config["APP_NAME"],
        "company_name": empresa,
        "company_initial": inicial,
        "portal_subtitle": app.config["PORTAL_SUBTITLE"],
        "ai_assistant_name": app.config["AI_ASSISTANT_NAME"],
        "default_admin_email": DEFAULT_ADMIN_EMAIL,
    }


@app.context_processor
def injetar_usuario():
    u = usuario_atual()
    contexto = {
        **_branding_context(),
        "usuario_logado": u,
        "abas_visiveis": set(),
        "pode_gerenciar_portal": False,
        "notificacoes_recentes": [],
        "notificacoes_nao_lidas": 0,
        "popup_pendente": None,
        "unidade_usuario": None,
    }
    if not u:
        return contexto
    contexto.update(
        abas_visiveis={aba["chave"] for aba in comunicados_model.listar_abas(u)},
        pode_gerenciar_portal=comunicados_model.usuario_eh_gestor(u),
        notificacoes_recentes=comunicados_model.listar_notificacoes(u["id"], limite=12),
        notificacoes_nao_lidas=comunicados_model.contar_nao_lidas(u["id"]),
        popup_pendente=comunicados_model.popup_pendente(u["id"]),
        unidade_usuario=unidades_model.unidade_do_usuario(u["id"]),
    )
    return contexto


def _notificacao_para_json(notificacao):
    icones = {
        "noticia": "fa-solid fa-newspaper",
        "pop": "fa-solid fa-book",
        "evento": "fa-solid fa-calendar-check",
        "comunicado": "fa-solid fa-bullhorn",
        "urgente": "fa-solid fa-triangle-exclamation",
    }
    return {
        "id": notificacao["id"],
        "tipo": notificacao["tipo"] or "informacao",
        "titulo": notificacao["titulo"] or "Atualização no portal",
        "mensagem": notificacao["mensagem"] or "",
        "criado_em": notificacao["criado_em"] or "",
        "lida": bool(notificacao["lida_em"]),
        "icone": icones.get(notificacao["tipo"], "fa-solid fa-bullhorn"),
        "url": url_for("notificacao_abrir", notificacao_id=notificacao["id"]),
    }


def _popup_para_json(comunicado):
    if not comunicado:
        return None
    icones = {
        "atencao": "fa-solid fa-circle-exclamation",
        "urgente": "fa-solid fa-triangle-exclamation",
    }
    return {
        "id": comunicado["id"],
        "tipo": comunicado["tipo"] or "informacao",
        "titulo": comunicado["titulo"] or "Comunicado",
        "mensagem": comunicado["mensagem"] or "",
        "link_url": comunicado["link_url"] or "",
        "icone": icones.get(comunicado["tipo"], "fa-solid fa-bullhorn"),
        "fechar_url": url_for("comunicado_fechar_popup", comunicado_id=comunicado["id"]),
    }


def _area_por_caminho(caminho):
    caminho = (caminho or "/").split("?", 1)[0]
    if caminho == "/":
        return "home"
    prefixos = (
        ("/comunicados", "comunicados"),
        ("/noticias", "noticias"),
        ("/pops", "pops"),
        ("/apps", "apps"),
        ("/admin/apps", "apps"),
        ("/agenda", "agenda"),
        ("/reservas", "agenda"),
        ("/chat", "chat"),
        ("/ti/chamados", "chamados_ti"),
        ("/ia", "ia"),
        ("/admin/atendimentos", "atendimentos"),
        ("/ti/estoque", "estoque"),
        ("/admin/usuarios", "usuarios"),
        ("/admin/acessos", "acessos"),
        ("/admin/honeypot", "honeypot"),
    )
    for prefixo, area in prefixos:
        if caminho == prefixo or caminho.startswith(f"{prefixo}/"):
            return area
    return "geral"


def _estado_sql(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    if not row:
        return "0:0:"
    return f"{row['total'] or 0}:{row['max_id'] or 0}:{row['max_data'] or ''}"


def _versoes_portal(usuario):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    estados = {
        "comunicados": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(COALESCE(atualizado_em, criado_em)), '') max_data
            FROM comunicados
            WHERE excluido_em IS NULL
              AND ativo = 1
              AND (inicio_em IS NULL OR datetime(inicio_em) <= datetime('now', 'localtime'))
              AND (fim_em IS NULL OR datetime(fim_em) >= datetime('now', 'localtime'))
            """,
        ),
        "noticias": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(criado_em), '') max_data
            FROM noticias
            WHERE excluido_em IS NULL
            """,
        ),
        "pops": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(criado_em), '') max_data
            FROM pops
            WHERE excluido_em IS NULL
            """,
        ),
        "apps": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(criado_em), '') max_data
            FROM hub_apps
            WHERE ativo = 1 AND excluido_em IS NULL
            """,
        ),
        "agenda": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(criado_em), '') max_data
            FROM eventos_agenda
            WHERE excluido_em IS NULL
            """,
        ),
        "chat": _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(criado_em), '') max_data
            FROM chat_mensagens
            WHERE apagada = 0
            """,
        ),
    }
    if usuario and usuario["role"] in ("admin", "superadmin"):
        estados["chamados_ti"] = _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(COALESCE(atualizado_em, criado_em)), '') max_data
            FROM chamados_ti
            WHERE excluido_em IS NULL
            """,
        )
    else:
        estados["chamados_ti"] = _estado_sql(
            conn,
            """
            SELECT COUNT(*) total,
                   COALESCE(MAX(id), 0) max_id,
                   COALESCE(MAX(COALESCE(atualizado_em, criado_em)), '') max_data
            FROM chamados_ti
            WHERE usuario_id = ? AND excluido_em IS NULL
            """,
            (usuario["id"] if usuario else 0,),
        )
    abas_estado = conn.execute(
        """
        SELECT COALESCE(GROUP_CONCAT(chave || ':' || habilitada_comum, '|'), '') estado
        FROM (
            SELECT chave, habilitada_comum
            FROM configuracao_abas
            ORDER BY ordem, chave
        )
        """
    ).fetchone()["estado"]
    conn.close()
    estados["abas"] = abas_estado
    estados["home"] = "|".join(
        estados[chave]
        for chave in ("comunicados", "noticias", "pops", "apps", "agenda", "chamados_ti", "abas")
    )
    estados["geral"] = "|".join(estados.values())
    estados["ia"] = estados["abas"]
    estados["atendimentos"] = estados["geral"]
    estados["estoque"] = estados["geral"]
    estados["usuarios"] = estados["geral"]
    estados["acessos"] = estados["geral"]
    estados["honeypot"] = estados["geral"]
    return estados


# ══════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════

# ── AUTH ──────────────────────────────────────────────────
@app.route("/admin", methods=["GET", "POST"])
@app.route("/painel", methods=["GET", "POST"])
@app.route("/wp-admin", methods=["GET", "POST"])
@app.route("/phpmyadmin", methods=["GET", "POST"])
@app.route("/admin_painel", methods=["GET", "POST"])
def admin_painel():
    email_tentado = request.form.get("email", "").strip() if request.method == "POST" else ""
    senha_texto = request.form.get("senha", "") if request.method == "POST" else ""
    if request.method == "POST":
        time.sleep(1.5)
    _log_honeypot_admin_painel(email_tentado, senha_texto)
    honeypot_fake_model.registrar(_obter_ip(), request.headers.get("User-Agent", ""), request.path, "login_submit" if request.method == "POST" else "login_view", email_tentado)

    erro = request.method == "POST"
    titulos = {
        "/admin": "Admin",
        "/painel": "Painel Administrativo",
        "/wp-admin": "WordPress Admin",
        "/phpmyadmin": "phpMyAdmin",
        "/admin_painel": "Admin Painel",
    }
    titulo = titulos.get(request.path, "Admin Painel")
    if request.method == "POST" and email_tentado and senha_texto:
        session["honeypot_fake_user"] = email_tentado
        return redirect(url_for("honeypot_dashboard"))
    return render_template("honeypot/login.html", titulo=titulo, erro=erro), 200


def _fake_user():
    return session.get("honeypot_fake_user") or DEFAULT_ADMIN_EMAIL


def _fake_track(acao, detalhe=""):
    honeypot_fake_model.registrar(_obter_ip(), request.headers.get("User-Agent", ""), request.path, acao, detalhe)


@app.route("/admin_painel/dashboard")
def honeypot_dashboard():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), "")
    _fake_track("view_dashboard")
    return render_template("honeypot/dashboard.html", dados=honeypot_fake_model.dashboard(), fake_user=_fake_user(), titulo="Dashboard")


@app.route("/admin_painel/users")
def honeypot_users():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), "")
    _fake_track("view_users")
    return render_template(
        "honeypot/table.html",
        titulo="Usuarios",
        subtitulo="Usuarios administrativos e contas de servico.",
        fake_user=_fake_user(),
        linhas=honeypot_fake_model.listar("users"),
        colunas=["ID", "Nome", "E-mail", "Role", "Status", "Ultimo login"],
        chaves=["id", "nome", "email", "role", "status", "ultimo_login"],
    )


@app.route("/admin_painel/tickets")
def honeypot_tickets():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), "")
    _fake_track("view_tickets")
    return render_template(
        "honeypot/table.html",
        titulo="Tickets",
        subtitulo="Fila operacional do painel administrativo.",
        fake_user=_fake_user(),
        linhas=honeypot_fake_model.listar("tickets"),
        colunas=["ID", "Titulo", "Cliente", "Prioridade", "Status", "Responsavel", "Criado em"],
        chaves=["id", "titulo", "cliente", "prioridade", "status", "responsavel", "criado_em"],
    )


@app.route("/admin_painel/logs")
def honeypot_logs():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), "")
    _fake_track("view_logs")
    return render_template(
        "honeypot/table.html",
        titulo="Logs",
        subtitulo="Eventos recentes do ambiente administrativo.",
        fake_user=_fake_user(),
        linhas=honeypot_fake_model.listar("logs"),
        colunas=["ID", "Nivel", "Origem", "Mensagem", "Criado em"],
        chaves=["id", "nivel", "origem", "mensagem", "criado_em"],
    )


@app.route("/admin_painel/backups")
def honeypot_backups():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), "")
    _fake_track("view_backups")
    return render_template(
        "honeypot/table.html",
        titulo="Backups",
        subtitulo="Arquivos de backup disponiveis para recuperacao.",
        fake_user=_fake_user(),
        linhas=honeypot_fake_model.listar("backups"),
        colunas=["ID", "Arquivo", "Tamanho", "Status", "Criado em"],
        chaves=["id", "arquivo", "tamanho", "status", "criado_em"],
    )


@app.route("/admin_painel/database", methods=["GET", "POST"])
def honeypot_database():
    if not session.get("honeypot_fake_user"):
        return redirect(url_for("admin_painel"))
    _log_honeypot_admin_painel(session.get("honeypot_fake_user"), request.form.get("acao", ""))
    _fake_track("database_action" if request.method == "POST" else "view_database", request.form.get("acao", ""))
    return render_template("honeypot/database.html", fake_user=_fake_user(), titulo="Database", erro=request.method == "POST")


@app.route("/admin_painel/logout")
def honeypot_logout():
    _fake_track("logout", session.get("honeypot_fake_user", ""))
    session.pop("honeypot_fake_user", None)
    return redirect(url_for("admin_painel"))

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
        session.clear()
        session["usuario_id"] = u["id"]
        return redirect(_destino_interno(request.args.get("proximo")))
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    u = usuario_atual()
    if u: _log_login("LOGOUT", u["email"])
    session.clear()
    flash("Você saiu.", "sucesso")
    return redirect(url_for("login"))


@app.route("/portal-notifications-sw.js")
def portal_notifications_sw():
    resposta = send_file(
        Path(app.root_path) / "static" / "portal-notifications-sw.js",
        mimetype="application/javascript",
        max_age=0,
    )
    resposta.headers["Service-Worker-Allowed"] = "/"
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# ── HOME ──────────────────────────────────────────────────
def _linha_para_dict(row):
    return {key: row[key] for key in row.keys()}


def _noticia_tem_imagem(noticia):
    return _noticia_eh_imagem(noticia) and _resolver_arquivo_noticia(noticia) is not None


def _noticias_home(limite=3):
    noticias = []
    for row in noticias_model.listar_noticias(limite=limite):
        item = _linha_para_dict(row)
        item["anexo_eh_imagem"] = _noticia_tem_imagem(item)
        noticias.append(item)
    return noticias


def _texto_parece_dica_ti(row):
    texto = " ".join(str(row[key] or "") for key in row.keys() if key in ("titulo", "resumo", "conteudo", "categoria"))
    texto = texto.lower().replace(".", "").replace("-", " ")
    texto_normalizado = texto.replace("_", " ")
    return (
        "dica ti" in texto_normalizado
        or "dicas da ti" in texto_normalizado
        or "dica da ti" in texto_normalizado
        or "dica tecnologia" in texto_normalizado
        or "orientacao ti" in texto_normalizado
        or "orientacoes ti" in texto_normalizado
    )


def _dicas_ti_home(limite=2):
    dicas_ti = []
    vistos = set()

    for pop in pops_model.listar_pops():
        if len(dicas_ti) >= limite:
            break
        categoria = (pop["categoria"] or "").lower().replace(".", "").strip()
        categoria_normalizada = categoria.replace("_", " ").replace("-", " ")
        if categoria_normalizada in {"dica ti", "dicas ti", "dicas da ti", "dica da ti"} or _texto_parece_dica_ti(pop):
            chave = ("pop", pop["id"])
            if chave in vistos:
                continue
            vistos.add(chave)
            dicas_ti.append({
                "tipo": "POP",
                "titulo": pop["titulo"],
                "data": pop["criado_em"][:10] if pop["criado_em"] else "",
                "url": url_for("pops_visualizar", pid=pop["id"]),
            })

    for noticia in noticias_model.listar_noticias(limite=12):
        if len(dicas_ti) >= limite:
            break
        if not _texto_parece_dica_ti(noticia):
            continue
        chave = ("noticia", noticia["id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        dicas_ti.append({
            "tipo": "Noticia",
            "titulo": noticia["titulo"],
            "data": noticia["criado_em"][:10] if noticia["criado_em"] else "",
            "url": url_for("noticia_detalhe", nid=noticia["id"]),
        })

    return dicas_ti


def _pode_ver_gerencial_atendimentos(usuario):
    if not usuario or not usuario["ativo"]:
        return False
    return usuario["role"] in ("admin", "superadmin") or atendimentos_model.setor_e_gerencial(usuario["setor"] or "")


def _gestao_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = usuario_atual()
        if not comunicados_model.usuario_eh_gestor(u):
            flash("Apenas administradores e a Gerência podem realizar esta ação.", "erro")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/api/pesquisa")
def api_pesquisa():
    termo = request.args.get("q", "").strip()
    if len(termo) < 2:
        return jsonify(resultados=[])

    u = usuario_atual()
    termo_like = f"%{termo}%"
    resultados = []
    vistos = set()

    def adicionar(tipo, titulo, descricao, url, icone):
        chave = (tipo, url)
        if chave in vistos or len(resultados) >= 18:
            return
        vistos.add(chave)
        resultados.append({
            "tipo": tipo,
            "titulo": titulo,
            "descricao": descricao or "",
            "url": url,
            "icone": icone,
        })

    for aba in comunicados_model.listar_abas(u):
        if termo.lower() in aba["nome"].lower():
            adicionar("Área", aba["nome"], "Abrir área do portal",
                      url_for(aba["endpoint"]), aba["icone"])
    if "comunicado" in termo.lower() or "aviso" in termo.lower():
        adicionar("Área", "Comunicados", "Avisos e atualizações do portal",
                  url_for("comunicados"), "fa-solid fa-bullhorn")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if comunicados_model.usuario_pode_acessar_aba(u, "noticias"):
        rows = conn.execute(
            """
            SELECT id, titulo, resumo FROM noticias
            WHERE excluido_em IS NULL
              AND (titulo LIKE ? OR resumo LIKE ? OR conteudo LIKE ?)
            ORDER BY criado_em DESC LIMIT 6
            """,
            (termo_like, termo_like, termo_like),
        ).fetchall()
        for row in rows:
            adicionar("Notícia", row["titulo"], row["resumo"],
                      url_for("noticia_detalhe", nid=row["id"]), "fa-solid fa-newspaper")

    if comunicados_model.usuario_pode_acessar_aba(u, "pops"):
        rows = conn.execute(
            """
            SELECT id, titulo, categoria FROM pops
            WHERE excluido_em IS NULL
              AND (titulo LIKE ? OR categoria LIKE ? OR conteudo_texto LIKE ?)
            ORDER BY criado_em DESC LIMIT 6
            """,
            (termo_like, termo_like, termo_like),
        ).fetchall()
        for row in rows:
            adicionar("POP", row["titulo"], row["categoria"],
                      url_for("pops_visualizar", pid=row["id"]), "fa-solid fa-book")

    rows = conn.execute(
        """
        SELECT id, titulo, mensagem FROM comunicados
        WHERE excluido_em IS NULL
          AND ativo = 1
          AND (inicio_em IS NULL OR datetime(inicio_em) <= datetime('now', 'localtime'))
          AND (fim_em IS NULL OR datetime(fim_em) >= datetime('now', 'localtime'))
          AND (titulo LIKE ? OR mensagem LIKE ?)
        ORDER BY criado_em DESC LIMIT 5
        """,
        (termo_like, termo_like),
    ).fetchall()
    for row in rows:
        adicionar("Comunicado", row["titulo"], row["mensagem"],
                  f"{url_for('comunicados')}#{row['id']}", "fa-solid fa-bullhorn")
    conn.close()

    if comunicados_model.usuario_pode_acessar_aba(u, "apps"):
        for app_hub in hub_model.listar_apps_para_usuario(u, apenas_ativos=True):
            texto = f"{app_hub['nome']} {app_hub['descricao'] or ''} {app_hub['setor'] or ''}".lower()
            if termo.lower() in texto:
                adicionar("App", app_hub["nome"], app_hub["descricao"],
                          app_hub["url"], app_hub["icone"])

    return jsonify(resultados=resultados)


@app.route("/comunicados", methods=["GET", "POST"])
def comunicados():
    u = usuario_atual()
    pode_gerenciar = comunicados_model.usuario_eh_gestor(u)
    if request.method == "POST":
        if not pode_gerenciar:
            abort(403)
        acao = request.form.get("acao", "")
        if acao == "criar":
            titulo = request.form.get("titulo", "").strip()
            mensagem = request.form.get("mensagem", "").strip()
            tipo = request.form.get("tipo", "informacao")
            link_url = request.form.get("link_url", "").strip()
            inicio_em = request.form.get("inicio_em", "").replace("T", " ")
            fim_em = request.form.get("fim_em", "").replace("T", " ")
            if tipo not in ("informacao", "atencao", "urgente"):
                tipo = "informacao"
            if link_url and not (
                (link_url.startswith("/") and not link_url.startswith("//"))
                or link_url.startswith("https://")
                or link_url.startswith("http://")
            ):
                flash("O link deve começar com /, http:// ou https://.", "erro")
                return redirect(url_for("comunicados"))
            if inicio_em and fim_em and fim_em < inicio_em:
                flash("A data final precisa ser posterior à data inicial.", "erro")
                return redirect(url_for("comunicados"))
            if not titulo or not mensagem:
                flash("Informe o título e a mensagem do comunicado.", "erro")
            else:
                comunicado_id = comunicados_model.criar_comunicado(
                    titulo,
                    mensagem,
                    tipo,
                    request.form.get("exibir_popup") == "1",
                    link_url,
                    inicio_em,
                    fim_em,
                    u["id"],
                    u["nome"],
                )
                _auditar(
                    "criar", "comunicados", comunicado_id,
                    novo=comunicados_model.buscar_comunicado(comunicado_id),
                )
                flash(f"Comunicado #{comunicado_id} publicado.", "sucesso")
        elif acao == "alternar":
            comunicado_id = request.form.get("comunicado_id", type=int)
            anterior = comunicados_model.buscar_comunicado(comunicado_id)
            comunicados_model.alternar_comunicado(comunicado_id)
            _auditar(
                "alterar_status", "comunicados", comunicado_id,
                anterior=anterior, novo=comunicados_model.buscar_comunicado(comunicado_id),
            )
            flash("Status do comunicado atualizado.", "sucesso")
        elif acao == "excluir":
            comunicado_id = request.form.get("comunicado_id", type=int)
            anterior = comunicados_model.buscar_comunicado(comunicado_id)
            comunicados_model.excluir_comunicado(comunicado_id)
            _auditar(
                "remover_logicamente", "comunicados", comunicado_id,
                anterior=anterior,
                novo=comunicados_model.buscar_comunicado(comunicado_id, incluir_excluido=True),
            )
            flash("Comunicado removido do mural e dos pop-ups.", "sucesso")
        elif acao == "salvar_abas":
            anterior = [_snapshot(aba) for aba in comunicados_model.listar_abas()]
            habilitadas = request.form.getlist("abas_habilitadas")
            comunicados_model.salvar_abas_comuns(habilitadas)
            _auditar(
                "alterar_permissoes", "configuracao_abas", "usuarios_comuns",
                anterior=anterior,
                novo=[_snapshot(aba) for aba in comunicados_model.listar_abas()],
            )
            flash("Acesso dos usuários comuns atualizado.", "sucesso")
        return redirect(url_for("comunicados"))

    return render_template(
        "comunicados.html",
        comunicados=comunicados_model.listar_comunicados(
            u["id"], incluir_inativos=pode_gerenciar
        ),
        abas_configuraveis=comunicados_model.listar_abas() if pode_gerenciar else [],
        pode_gerenciar=pode_gerenciar,
        agora_local=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/comunicados/<int:comunicado_id>/fechar-popup", methods=["POST"])
def comunicado_fechar_popup(comunicado_id):
    u = usuario_atual()
    comunicados_model.fechar_popup(comunicado_id, u["id"])
    return jsonify(sucesso=True)


@app.route("/notificacoes/<int:notificacao_id>/abrir")
def notificacao_abrir(notificacao_id):
    u = usuario_atual()
    notificacao = comunicados_model.buscar_notificacao(notificacao_id)
    if not notificacao:
        abort(404)
    comunicados_model.marcar_notificacao_lida(notificacao_id, u["id"])
    destino = (notificacao["url"] or "").strip()
    if not destino or destino.startswith("//") or not destino.startswith("/"):
        destino = url_for("comunicados")
    return redirect(destino)


@app.route("/notificacoes/marcar-todas", methods=["POST"])
def notificacoes_marcar_todas():
    u = usuario_atual()
    comunicados_model.marcar_todas_lidas(u["id"])
    return redirect(_destino_interno(request.referrer))


@app.route("/api/notificacoes/resumo")
def api_notificacoes_resumo():
    u = usuario_atual()
    return jsonify(nao_lidas=comunicados_model.contar_nao_lidas(u["id"]))


@app.route("/api/portal/tempo-real")
def api_portal_tempo_real():
    u = usuario_atual()
    notificacoes = comunicados_model.listar_notificacoes(u["id"], limite=12)
    popup = comunicados_model.popup_pendente(u["id"])
    abas = comunicados_model.listar_abas(u)
    versoes = _versoes_portal(u)
    caminho = request.args.get("path") or request.path
    area = _area_por_caminho(caminho)
    acesso_atual = True
    if area in {chave for chave, *_ in comunicados_model.ABAS_PADRAO}:
        acesso_atual = comunicados_model.usuario_pode_acessar_aba(u, area)
    total_nao_lidas = comunicados_model.contar_nao_lidas(u["id"])
    return jsonify(
        agora=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        area=area,
        versao=versoes.get(area, versoes["geral"]),
        acesso_atual=acesso_atual,
        poll_ms=12000,
        nao_lidas=total_nao_lidas,
        nao_lidas_label="99+" if total_nao_lidas > 99 else str(total_nao_lidas),
        notificacoes=[_notificacao_para_json(n) for n in notificacoes],
        popup=_popup_para_json(popup),
        abas=[
            {
                "chave": aba["chave"],
                "nome": aba["nome"],
                "endpoint": aba["endpoint"],
                "icone": aba["icone"],
            }
            for aba in abas
        ],
    )


@app.route("/")
def home():
    u = usuario_atual()
    setor_usuario = (u["setor"] or "").strip() if u else ""
    usuario_ve_todos_setores = _pode_ver_gerencial_atendimentos(u)
    setor_filtro_indicadores = None if usuario_ve_todos_setores else setor_usuario
    if usuario_ve_todos_setores or setor_filtro_indicadores:
        atendimento_top_qtd = atendimentos_model.top_qtd(10, setor_filtro_indicadores)
        atendimento_top_tempo = atendimentos_model.top_tempo(10, setor_filtro_indicadores)
        atendimento_resumo = atendimentos_model.resumo(setor_filtro_indicadores)
        indicadores_home = atendimentos_model.indicadores_gerais(setor_filtro_indicadores)
    else:
        atendimento_top_qtd = []
        atendimento_top_tempo = []
        atendimento_resumo = {"pessoas": 0, "total": 0, "ultima": None}
        indicadores_home = atendimentos_model.indicadores_gerais("__sem_setor__")
        indicadores_home["setor"] = "Sem setor"
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    agenda_hoje = conn.execute(
        """
        SELECT * FROM eventos_agenda
        WHERE excluido_em IS NULL
          AND date(data_evento) = ? AND COALESCE(tipo, 'reserva') = 'reserva'
        ORDER BY sala, hora_inicio, titulo
        LIMIT 2
        """,
        (date.today().isoformat(),)
    ).fetchall()
    conn.close()
    return render_template("index.html",
        total_apps=hub_model.contar_apps(u),
        total_pops=pops_model.contar_pops(),
        total_usuarios=usuarios_model.contar_usuarios(),
        noticias=_noticias_home(limite=3),
        dicas_ti=_dicas_ti_home(limite=2),
        pops_recentes=pops_model.listar_pops()[:2],
        agenda_hoje=agenda_hoje,
        proximos_eventos_internos=agenda_model.proximos_eventos_internos(2),
        atendimento_top_qtd=atendimento_top_qtd,
        atendimento_top_tempo=atendimento_top_tempo,
        atendimento_resumo=atendimento_resumo,
        indicadores_home=indicadores_home,
        setor_indicadores="Todos os setores" if usuario_ve_todos_setores else (setor_usuario or "Sem setor"),
        pode_ver_gerencial_atendimentos=_pode_ver_gerencial_atendimentos(u),
        apps_hub=hub_model.listar_apps_para_usuario(u, apenas_ativos=True)[:6]
    )

# ── CHAT ─────────────────────────────────────────────────
@app.route("/chat", methods=["GET", "POST"])
def chat():
    u = usuario_atual()
    if request.method == "POST":
        mensagem = request.form.get("mensagem", "").strip()
        if not mensagem:
            flash("Digite uma mensagem antes de enviar.", "erro")
            return redirect(url_for("chat"))
        chat_model.criar_mensagem(u["id"], u["nome"], mensagem)
        _log_chat("ENVIO", u, mensagem)
        return redirect(url_for("chat"))

    pode_ver_apagadas = u and u["role"] in ("admin", "superadmin")
    mensagens = chat_model.listar_mensagens(incluir_apagadas=pode_ver_apagadas)
    return render_template("chat.html", mensagens=mensagens, pode_ver_apagadas=pode_ver_apagadas)

def _chat_msg_json(msg):
    return {
        "id": msg["id"],
        "usuario_id": msg["usuario_id"],
        "usuario_nome": msg["usuario_nome"],
        "mensagem": msg["mensagem"],
        "apagada": bool(msg["apagada"]),
        "apagada_em": msg["apagada_em"],
        "apagada_por_nome": msg["apagada_por_nome"],
        "criado_em": msg["criado_em"],
    }

@app.route("/api/chat/mensagens")
def api_chat_mensagens():
    u = usuario_atual()
    pode_ver_apagadas = u and u["role"] in ("admin", "superadmin")
    mensagens = chat_model.listar_mensagens(incluir_apagadas=pode_ver_apagadas)
    return jsonify(
        mensagens=[_chat_msg_json(m) for m in mensagens],
        usuario={"id": u["id"], "nome": u["nome"], "role": u["role"]},
        pode_ver_apagadas=pode_ver_apagadas,
    )

@app.route("/api/chat/enviar", methods=["POST"])
def api_chat_enviar():
    u = usuario_atual()
    dados = request.get_json(silent=True) or {}
    mensagem = (dados.get("mensagem") or "").strip()
    if not mensagem:
        return jsonify(sucesso=False, erro="Mensagem vazia."), 400
    mid = chat_model.criar_mensagem(u["id"], u["nome"], mensagem)
    _log_chat("ENVIO", u, mensagem)
    msg = chat_model.buscar_mensagem(mid)
    return jsonify(sucesso=True, mensagem=_chat_msg_json(msg))

@app.route("/chat/<int:mid>/apagar", methods=["POST"])
def chat_apagar(mid):
    u = usuario_atual()
    msg = chat_model.buscar_mensagem(mid)
    if not msg:
        abort(404)
    pode_apagar = (msg["usuario_id"] == u["id"]) or u["role"] in ("admin", "superadmin")
    if not pode_apagar:
        flash("Voce so pode apagar suas proprias mensagens.", "erro")
        return redirect(url_for("chat"))
    if not msg["apagada"]:
        chat_model.apagar_mensagem(mid, u["id"], u["nome"])
        _log_chat("APAGOU", u, f"id={mid} | autor={msg['usuario_nome']} | original={msg['mensagem']}")
        _auditar(
            "remover_logicamente", "chat", mid, anterior=msg,
            novo=chat_model.buscar_mensagem(mid),
        )
    return redirect(url_for("chat"))

@app.route("/api/chat/<int:mid>/apagar", methods=["POST"])
def api_chat_apagar(mid):
    u = usuario_atual()
    msg = chat_model.buscar_mensagem(mid)
    if not msg:
        return jsonify(sucesso=False, erro="Mensagem nao encontrada."), 404
    pode_apagar = (msg["usuario_id"] == u["id"]) or u["role"] in ("admin", "superadmin")
    if not pode_apagar:
        return jsonify(sucesso=False, erro="Permissao insuficiente."), 403
    if not msg["apagada"]:
        chat_model.apagar_mensagem(mid, u["id"], u["nome"])
        _log_chat("APAGOU", u, f"id={mid} | autor={msg['usuario_nome']} | original={msg['mensagem']}")
        _auditar(
            "remover_logicamente", "chat", mid, anterior=msg,
            novo=chat_model.buscar_mensagem(mid),
        )
    return jsonify(sucesso=True)

# ── NOTÍCIAS ─────────────────────────────────────────────
@app.route("/noticias")
def noticias():
    return render_template("noticias.html", noticias=noticias_model.listar_noticias())

@app.route("/noticias/<int:nid>")
def noticia_detalhe(nid):
    noticia = noticias_model.buscar_noticia_por_id(nid)
    if not noticia: abort(404)
    anexo_eh_imagem = _noticia_eh_imagem(noticia) and _resolver_arquivo_noticia(noticia) is not None
    return render_template("noticia_detalhe.html", noticia=noticia, anexo_eh_imagem=anexo_eh_imagem)

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
    nid = noticias_model.criar_noticia(
        titulo, resumo, conteudo, u["nome"] if u else "Admin",
        caminho_anexo, nome_anexo
    )
    _auditar("criar", "noticias", nid, novo=noticias_model.buscar_noticia_por_id(nid))
    comunicados_model.criar_notificacao(
        "noticia",
        f"Nova notícia: {titulo}",
        resumo,
        url_for("noticia_detalhe", nid=nid),
        "noticia",
        nid,
    )
    flash("Notícia publicada!", "sucesso")
    return redirect(url_for("noticias"))

@app.route("/noticias/<int:nid>/anexo")
def noticias_anexo(nid):
    n = noticias_model.buscar_noticia_por_id(nid)
    arquivo = _resolver_arquivo_noticia(n)
    if not arquivo: abort(404)
    return send_file(arquivo, as_attachment=True, download_name=n["nome_anexo"] or arquivo.name)

@app.route("/noticias/<int:nid>/midia")
def noticias_midia(nid):
    n = noticias_model.buscar_noticia_por_id(nid)
    arquivo = _resolver_arquivo_noticia(n)
    if not arquivo or not _noticia_eh_imagem(n):
        abort(404)
    return send_file(arquivo, download_name=n["nome_anexo"] or arquivo.name)

@app.route("/noticias/<int:nid>/excluir", methods=["POST"])
@admin_required
def noticias_excluir(nid):
    anterior = noticias_model.buscar_noticia_por_id(nid)
    noticias_model.excluir_noticia(nid)
    _auditar(
        "remover_logicamente", "noticias", nid, anterior=anterior,
        novo={"id": nid, "estado": "removido_logicamente"},
    )
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
    salas_admin = conn.execute("SELECT * FROM salas WHERE excluido_em IS NULL ORDER BY nome").fetchall()
    salas = [r["nome"] for r in salas_admin]
    eventos_proximos = conn.execute(
        """
        SELECT * FROM eventos_agenda
        WHERE excluido_em IS NULL AND date(data_evento) >= date('now')
        ORDER BY sala, data_evento, hora_inicio
        LIMIT 60
        """
    ).fetchall()
    conn.close()
    eventos_por_sala = {}
    for evento in eventos_proximos:
        eventos_por_sala.setdefault(evento["sala"], []).append(evento)
    return render_template(
        "agenda.html",
        ano=ano,
        mes=mes,
        salas=salas,
        salas_admin=salas_admin,
        eventos_por_sala=eventos_por_sala,
        unidades=unidades_model.listar_unidades(apenas_ativas=True),
        unidades_salas=unidades_model.unidades_por_registro("salas"),
    )

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
        "tipo": e["tipo"] if "tipo" in e.keys() else "reserva",
        "cor": agenda_model.cor_do_evento(e["tipo"] if "tipo" in e.keys() else "reserva", e["sala"]),
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
    tipo        = request.form.get("tipo","reserva").strip()
    if tipo not in ("reserva", "interno"):
        tipo = "reserva"
    if tipo == "interno" and sala == "Geral":
        sala = "Evento interno"
    if not titulo or not data_evento:
        flash("Informe titulo e data.", "erro")
        return redirect(url_for("agenda"))
    u = usuario_atual()
    eid = agenda_model.criar_evento(
        titulo, descricao, data_evento, hora_inicio, hora_fim, sala,
        u["nome"] if u else "Sistema", tipo
    )
    unidade = _unidade_da_sala(sala)
    unidades_model.vincular_registro(
        "eventos_agenda", eid, unidade["id"] if unidade else None,
        "unidade" if unidade else ("compartilhado" if tipo == "interno" else "nao_definido"),
        u["id"] if u else None,
    )
    _auditar(
        "criar", "agenda", eid, novo=agenda_model.buscar_evento_por_id(eid), unidade=unidade,
    )
    if tipo == "interno":
        comunicados_model.criar_notificacao(
            "evento",
            f"Novo evento: {titulo}",
            f"{data_evento}{f' às {hora_inicio}' if hora_inicio else ''}",
            url_for("agenda"),
            "evento",
            eid,
        )
    flash("Evento adicionado.", "sucesso")
    ano, mes, _ = data_evento.split("-")
    return redirect(url_for("agenda", ano=int(ano), mes=int(mes)))

@app.route("/agenda/<int:eid>/editar", methods=["POST"])
@recepcao_required
def agenda_editar(eid):
    anterior = agenda_model.buscar_evento_por_id(eid)
    titulo      = request.form.get("titulo","").strip()
    descricao   = request.form.get("descricao","").strip()
    data_evento = request.form.get("data","").strip()
    hora_inicio = request.form.get("hora_inicio","").strip() or None
    hora_fim    = request.form.get("hora_fim","").strip() or None
    sala        = request.form.get("sala","").strip() or "Geral"
    tipo        = request.form.get("tipo","reserva").strip()
    if tipo not in ("reserva", "interno"):
        tipo = "reserva"
    if tipo == "interno" and sala == "Geral":
        sala = "Evento interno"
    agenda_model.atualizar_evento(eid, titulo, descricao, data_evento, hora_inicio, hora_fim, sala, tipo)
    unidade = _unidade_da_sala(sala)
    unidades_model.vincular_registro(
        "eventos_agenda", eid, unidade["id"] if unidade else None,
        "unidade" if unidade else ("compartilhado" if tipo == "interno" else "nao_definido"),
        usuario_atual()["id"],
    )
    _auditar(
        "atualizar", "agenda", eid, anterior=anterior,
        novo=agenda_model.buscar_evento_por_id(eid), unidade=unidade,
    )
    flash("Evento atualizado.", "sucesso")
    ano, mes, _ = data_evento.split("-")
    return redirect(url_for("agenda", ano=int(ano), mes=int(mes)))

@app.route("/agenda/<int:eid>/excluir", methods=["POST"])
@recepcao_required
def agenda_excluir(eid):
    anterior = agenda_model.buscar_evento_por_id(eid)
    agenda_model.excluir_evento(eid)
    _auditar(
        "remover_logicamente", "agenda", eid, anterior=anterior,
        novo={"id": eid, "estado": "removido_logicamente"},
        unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("eventos_agenda", eid)),
    )
    flash("Evento removido.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/api/agenda/evento/<int:eid>")
def api_agenda_evento(eid):
    e = agenda_model.buscar_evento_por_id(eid)
    if not e: return jsonify(erro="Não encontrado."), 404
    return jsonify(dict(e))

@app.route("/admin/salas/criar", methods=["POST"])
@admin_required
def admin_salas_criar():
    nome = request.form.get("nome","").strip()
    capacidade = request.form.get("capacidade", type=int) or 0
    descricao = request.form.get("descricao","").strip()
    if not nome:
        flash("Informe o nome da sala.", "erro")
    elif salas_model.buscar_sala_por_nome(nome):
        flash("Essa sala ja existe.", "erro")
    else:
        sala_id = salas_model.criar_sala(nome, capacidade, descricao)
        unidade_id = request.form.get("unidade_id", type=int)
        unidades_model.vincular_registro(
            "salas", sala_id, unidade_id, "unidade" if unidade_id else "nao_definido",
            usuario_atual()["id"],
        )
        unidade = unidades_model.buscar_unidade(unidade_id)
        _auditar(
            "criar", "salas", sala_id, novo=salas_model.buscar_sala_por_id(sala_id), unidade=unidade,
        )
        flash("Sala adicionada.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/admin/salas/<int:sala_id>/atualizar", methods=["POST"])
@admin_required
def admin_salas_atualizar(sala_id):
    anterior = salas_model.buscar_sala_por_id(sala_id)
    nome = request.form.get("nome","").strip()
    capacidade = request.form.get("capacidade", type=int) or 0
    descricao = request.form.get("descricao","").strip()
    existente = salas_model.buscar_sala_por_nome(nome)
    if not nome:
        flash("Informe o nome da sala.", "erro")
    elif existente and existente["id"] != sala_id:
        flash("Ja existe outra sala com esse nome.", "erro")
    else:
        salas_model.atualizar_sala(sala_id, nome, capacidade, descricao)
        unidade_id = request.form.get("unidade_id", type=int)
        unidades_model.vincular_registro(
            "salas", sala_id, unidade_id, "unidade" if unidade_id else "nao_definido",
            usuario_atual()["id"],
        )
        unidade = unidades_model.buscar_unidade(unidade_id)
        _auditar(
            "atualizar", "salas", sala_id, anterior=anterior,
            novo=salas_model.buscar_sala_por_id(sala_id), unidade=unidade,
        )
        flash("Sala atualizada.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/admin/salas/<int:sala_id>/excluir", methods=["POST"])
@admin_required
def admin_salas_excluir(sala_id):
    anterior = salas_model.buscar_sala_por_id(sala_id)
    if salas_model.sala_tem_reservas(sala_id):
        flash("Nao foi possivel excluir: existem reservas vinculadas a esta sala.", "erro")
    else:
        salas_model.excluir_sala(sala_id)
        _auditar(
            "remover_logicamente", "salas", sala_id, anterior=anterior,
            novo={"id": sala_id, "estado": "removido_logicamente"},
            unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("salas", sala_id)),
        )
        flash("Sala removida.", "sucesso")
    return redirect(url_for("agenda"))

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

        cursor.execute("SELECT id FROM salas WHERE nome=? AND excluido_em IS NULL", (sala_nome,))
        sala = cursor.fetchone()
        sala_id = sala["id"] if sala else cursor.execute("INSERT INTO salas(nome) VALUES(?)",(sala_nome,)).lastrowid
        conn.commit()
        if not sala:
            unidades_model.vincular_registro(
                "salas", sala_id, None, "nao_definido", usuario_atual()["id"],
            )
            _auditar("criar", "salas", sala_id, novo=salas_model.buscar_sala_por_id(sala_id))

        cursor.execute(
            "SELECT id FROM reservas WHERE excluido_em IS NULL AND sala_id=? AND data_reserva=? AND NOT(hora_fim<=? OR hora_inicio>=?)",
            (sala_id, data_r, hi, hf))
        if cursor.fetchone():
            flash("Já existe reserva nesse horário.", "erro")
            conn.close(); return redirect(url_for("agenda"))

        cursor.execute(
            "INSERT INTO reservas(sala_id,titulo,responsavel,data_reserva,hora_inicio,hora_fim,observacao) VALUES(?,?,?,?,?,?,?)",
            (sala_id, titulo, responsavel, data_r, hi, hf, obs))
        reserva_id = cursor.lastrowid
        conn.commit()

        unidade = _unidade_da_sala(sala_nome)
        unidades_model.vincular_registro(
            "reservas", reserva_id, unidade["id"] if unidade else None,
            "unidade" if unidade else "nao_definido", usuario_atual()["id"],
        )
        reserva_nova = conn.execute("SELECT * FROM reservas WHERE id=?", (reserva_id,)).fetchone()
        _auditar("criar", "reservas", reserva_id, novo=reserva_nova, unidade=unidade)

        # Sincroniza com a agenda automaticamente
        descricao_evento = f"Reserva por {responsavel}" + (f" — {obs}" if obs else "")
        evento_id = agenda_model.criar_evento(titulo, descricao_evento, data_r, hi, hf, sala_nome, responsavel)
        unidades_model.vincular_registro(
            "eventos_agenda", evento_id, unidade["id"] if unidade else None,
            "unidade" if unidade else "nao_definido", usuario_atual()["id"],
        )
        _auditar("criar", "agenda", evento_id, novo=agenda_model.buscar_evento_por_id(evento_id), unidade=unidade,
                 detalhes={"origem": "reserva", "reserva_id": reserva_id})

        flash("Reserva criada e adicionada à agenda!", "sucesso")
        conn.close(); return redirect(url_for("agenda"))

    cursor.execute("SELECT nome FROM salas WHERE excluido_em IS NULL ORDER BY nome")
    salas = [r["nome"] for r in cursor.fetchall()]
    cursor.execute("""SELECT reservas.*,salas.nome AS sala_nome FROM reservas
        JOIN salas ON salas.id=reservas.sala_id
        WHERE reservas.excluido_em IS NULL AND salas.excluido_em IS NULL
          AND date(data_reserva)>=date('now')
        ORDER BY data_reserva,hora_inicio LIMIT 30""")
    lista = cursor.fetchall()
    conn.close()
    return render_template("reservas.html", reservas=lista, salas=salas)

@app.route("/reservas/<int:rid>/excluir", methods=["POST"])
@admin_required
def reservas_excluir(rid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    anterior = conn.execute("SELECT * FROM reservas WHERE id=? AND excluido_em IS NULL", (rid,)).fetchone()
    conn.execute("UPDATE reservas SET excluido_em=CURRENT_TIMESTAMP WHERE id=? AND excluido_em IS NULL", (rid,))
    conn.commit(); conn.close()
    _auditar(
        "remover_logicamente", "reservas", rid, anterior=anterior,
        novo={"id": rid, "estado": "removido_logicamente"},
        unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("reservas", rid)),
    )
    flash("Reserva excluída.", "sucesso")
    return redirect(url_for("agenda"))

@app.route("/reservas/<int:rid>/editar", methods=["POST"])
@admin_required
def reservas_editar(rid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    anterior = cursor.execute("SELECT * FROM reservas WHERE id=? AND excluido_em IS NULL", (rid,)).fetchone()
    titulo   = request.form.get("titulo","").strip()
    data_r   = request.form.get("data","").strip()
    hi       = request.form.get("hora_inicio","").strip()
    hf       = request.form.get("hora_fim","").strip()
    resp     = request.form.get("responsavel","").strip()
    obs      = request.form.get("observacao","").strip()
    cursor.execute(
        "UPDATE reservas SET titulo=?,responsavel=?,data_reserva=?,hora_inicio=?,hora_fim=?,observacao=? WHERE id=? AND excluido_em IS NULL",
        (titulo, resp, data_r, hi, hf, obs, rid))
    conn.commit()
    novo = cursor.execute("SELECT * FROM reservas WHERE id=? AND excluido_em IS NULL", (rid,)).fetchone()
    conn.close()
    _auditar(
        "atualizar", "reservas", rid, anterior=anterior, novo=novo,
        unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("reservas", rid)),
    )
    flash("Reserva atualizada.", "sucesso")
    return redirect(url_for("agenda"))

# ── POPS ─────────────────────────────────────────────────
@app.route("/pops")
def pops():
    busca     = request.args.get("q","").strip()
    categoria = request.args.get("cat","").strip()
    lista     = pops_model.listar_pops(busca=busca, categoria=categoria or None)
    return render_template("pops.html", pops=lista, busca=busca,
                           categoria=categoria, categorias=_categorias_pop_disponiveis())

@app.route("/pops/upload", methods=["POST"])
@admin_required
def pops_upload():
    arquivo   = request.files.get("arquivo")
    titulo    = request.form.get("titulo","").strip()
    categoria = request.form.get("categoria","").strip() or "Outros"
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo.", "erro"); return redirect(url_for("pops"))
    ext = Path(arquivo.filename).suffix.lower()
    if ext not in (".pdf",".docx",".txt"):
        flash("Formatos aceitos: PDF, DOCX, TXT.", "erro"); return redirect(url_for("pops"))
    if not titulo:
        titulo = Path(arquivo.filename).stem
    pasta = Path("static/uploads/pops")
    pasta.mkdir(parents=True, exist_ok=True)
    nome_original = secure_filename(arquivo.filename) or f"pop{ext}"
    nome_seg = f"{int(time.time())}_{nome_original}"
    caminho  = pasta / nome_seg
    try:
        arquivo.save(caminho)
    except OSError as e:
        flash(f"Nao foi possivel salvar o arquivo: {e}", "erro")
        return redirect(url_for("pops"))
    texto = pops_model.extrair_texto(caminho, ext)
    pop_id = pops_model.criar_pop(titulo, categoria, arquivo.filename, str(caminho), texto)
    _auditar("criar", "pops", pop_id, novo=pops_model.buscar_pop_por_id(pop_id))
    comunicados_model.criar_notificacao(
        "pop",
        f"Novo POP: {titulo}",
        f"Categoria: {categoria}",
        url_for("pops_visualizar", pid=pop_id),
        "pop",
        pop_id,
    )
    flash("POP enviado!", "sucesso")
    return redirect(url_for("pops"))

@app.route("/pops/<int:pid>/download")
def pops_download(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if not p: abort(404)
    arquivo = _resolver_arquivo_pop(p)
    if not arquivo:
        flash("Arquivo do POP nao encontrado no servidor. Reenvie o arquivo ou restaure static/uploads/pops do backup.", "erro")
        return redirect(url_for("pops_visualizar", pid=pid))
    return send_file(arquivo, as_attachment=True, download_name=p["nome_arquivo"])

@app.route("/pops/<int:pid>/visualizar")
def pops_visualizar(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if not p: abort(404)
    ext = Path(p["nome_arquivo"]).suffix.lower()
    if ext == ".pdf":
        arquivo = _resolver_arquivo_pop(p)
        if not arquivo:
            flash("Arquivo do POP nao encontrado no servidor. Reenvie o arquivo ou restaure static/uploads/pops do backup.", "erro")
            return render_template("pop_visualizar.html", pop=p, arquivo_disponivel=False)
        return send_file(arquivo, mimetype="application/pdf")
    # TXT / DOCX → mostra o texto extraído
    return render_template("pop_visualizar.html", pop=p, arquivo_disponivel=bool(_resolver_arquivo_pop(p)))

@app.route("/pops/<int:pid>/excluir", methods=["POST"])
@admin_required
def pops_excluir(pid):
    p = pops_model.buscar_pop_por_id(pid)
    if p:
        pops_model.excluir_pop(pid)
        _auditar(
            "remover_logicamente", "pops", pid, anterior=p,
            novo={"id": pid, "estado": "removido_logicamente", "arquivo_preservado": True},
        )
        flash("POP removido.", "sucesso")
    return redirect(url_for("pops"))

# ── HUB DE APPS ──────────────────────────────────────────
@app.route("/apps")
def hub_apps():
    por_setor = hub_model.listar_apps_por_setor_para_usuario(usuario_atual())
    setores   = sorted(por_setor.keys())
    return render_template("hub_apps.html", por_setor=por_setor, setores=setores)

@app.route("/apps/adf")
def app_adf():
    adf_url = os.environ.get("ADF_URL", "").strip()
    if adf_url:
        return redirect(adf_url)
    flash("URL do ADF ainda nao configurada. Ajuste o cadastro em Gerenciar Apps.", "erro")
    return redirect(url_for("hub_apps"))

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
        unidade = unidades_model.unidade_do_usuario(u["id"])
        chamado_id = chamados_model.criar_chamado(
            u["id"], u["nome"], titulo, descricao, prioridade,
            unidade_id=unidade["id"] if unidade else None,
            associado_por_id=u["id"],
        )
        _auditar("criar", "chamados_ti", chamado_id, novo=chamados_model.buscar_chamado(chamado_id), unidade=unidade)
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
        unidade_usuario=unidades_model.unidade_do_usuario(u["id"]),
        unidades_chamados=unidades_model.unidades_por_registro("chamados_ti"),
    )

@app.route("/ti/chamados/<int:chamado_id>/atualizar", methods=["POST"])
@admin_required
def chamados_ti_atualizar(chamado_id):
    anterior = chamados_model.buscar_chamado(chamado_id)
    responsavel = request.form.get("responsavel","").strip()
    resposta = request.form.get("resposta","").strip()
    status = request.form.get("status","em_atendimento").strip()
    try:
        ok = chamados_model.atualizar_atendimento(chamado_id, responsavel, resposta, status)
    except ValueError:
        ok = False
    if ok:
        _auditar(
            "atualizar", "chamados_ti", chamado_id, anterior=anterior,
            novo=chamados_model.buscar_chamado(chamado_id),
            unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("chamados_ti", chamado_id)),
        )
    flash("Chamado atualizado." if ok else "Nao foi possivel atualizar o chamado.", "sucesso" if ok else "erro")
    return redirect(url_for("chamados_ti"))

@app.route("/ti/chamados/<int:chamado_id>/excluir", methods=["POST"])
@admin_required
def chamados_ti_excluir(chamado_id):
    anterior = chamados_model.buscar_chamado(chamado_id)
    chamados_model.excluir_chamado(chamado_id)
    _auditar(
        "remover_logicamente", "chamados_ti", chamado_id, anterior=anterior,
        novo={"id": chamado_id, "estado": "removido_logicamente"},
        unidade=_unidade_do_vinculo(unidades_model.unidade_do_registro("chamados_ti", chamado_id)),
    )
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
                item_id = estoque_model.criar_item(nome, categoria, quantidade, localizacao, observacao)
                _auditar("criar", "estoque_ti", item_id, novo=estoque_model.buscar_item(item_id))
                flash("Item adicionado ao estoque.", "sucesso")
        elif acao == "atualizar":
            item_id = request.form.get("item_id", type=int)
            anterior = estoque_model.buscar_item(item_id)
            estoque_model.atualizar_item(
                item_id,
                request.form.get("nome",""),
                request.form.get("categoria","Perifericos"),
                request.form.get("quantidade", type=int) or 0,
                request.form.get("localizacao",""),
                request.form.get("observacao",""),
            )
            _auditar("atualizar", "estoque_ti", item_id, anterior=anterior, novo=estoque_model.buscar_item(item_id))
            flash("Item atualizado.", "sucesso")
        elif acao == "excluir":
            item_id = request.form.get("item_id", type=int)
            anterior = estoque_model.buscar_item(item_id)
            estoque_model.excluir_item(item_id)
            _auditar(
                "remover_logicamente", "estoque_ti", item_id, anterior=anterior,
                novo={"id": item_id, "estado": "removido_logicamente"},
            )
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
            app_id = hub_model.criar_app(
                request.form.get("nome",""),
                request.form.get("descricao",""),
                request.form.get("icone","fa-solid fa-mobile-screen"),
                request.form.get("url",""),
                request.form.get("setor","Geral"),
                request.form.get("setores_liberados",""),
            )
            _auditar("criar", "hub_apps", app_id, novo=hub_model.buscar_app_por_id(app_id))
            flash("App cadastrado.", "sucesso")
        elif acao == "excluir":
            app_id = request.form.get("app_id", type=int)
            anterior = hub_model.buscar_app_por_id(app_id)
            hub_model.excluir_app(app_id)
            _auditar(
                "remover_logicamente", "hub_apps", app_id, anterior=anterior,
                novo={"id": app_id, "estado": "removido_logicamente"},
            )
            flash("App removido.", "sucesso")
        elif acao == "toggle":
            app_id = request.form.get("app_id", type=int)
            anterior = hub_model.buscar_app_por_id(app_id)
            hub_model.alternar_ativo(app_id)
            _auditar("alterar_status", "hub_apps", app_id, anterior=anterior, novo=hub_model.buscar_app_por_id(app_id))
            flash("Status alterado.", "sucesso")
        elif acao == "atualizar":
            app_id = request.form.get("app_id", type=int)
            anterior = hub_model.buscar_app_por_id(app_id)
            hub_model.atualizar_app(
                app_id,
                request.form.get("nome",""),
                request.form.get("descricao",""),
                request.form.get("icone","fa-solid fa-mobile-screen"),
                request.form.get("url",""),
                request.form.get("setor","Geral"),
                request.form.get("setores_liberados",""),
            )
            _auditar("atualizar", "hub_apps", app_id, anterior=anterior, novo=hub_model.buscar_app_por_id(app_id))
            flash("App atualizado.", "sucesso")
        return redirect(url_for("admin_apps"))

    todos = hub_model.listar_apps(apenas_ativos=False)
    return render_template("admin_apps.html", apps=todos,
                           setores_conhecidos=["Fiscal","RH","Administrativo","TI","Automações","Comercial","Geral"])

# ── ADMIN ATENDIMENTOS ────────────────────────────────────
@app.route("/admin/atendimentos", methods=["GET", "POST"])
@login_required
def admin_atendimentos():
    u = usuario_atual()
    if not _pode_ver_gerencial_atendimentos(u):
        flash("Voce nao tem permissao para acessar os indicadores gerenciais.", "erro")
        return redirect(url_for("home"))

    pode_gerenciar = u["role"] in ("admin", "superadmin")
    setor_selecionado = request.values.get("setor", "").strip()

    if request.method == "POST":
        if not pode_gerenciar:
            flash("Somente administradores podem atualizar a planilha de atendimentos.", "erro")
            return redirect(url_for("admin_atendimentos", setor=setor_selecionado))
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            flash("Selecione uma planilha XLSX.", "erro")
            return redirect(url_for("admin_atendimentos", setor=setor_selecionado))
        ext = Path(arquivo.filename).suffix.lower()
        if ext not in (".xlsx", ".xls"):
            flash("Envie apenas arquivos Excel (.xlsx ou .xls).", "erro")
            return redirect(url_for("admin_atendimentos", setor=setor_selecionado))

        pasta = Path("static/uploads/atendimentos")
        pasta.mkdir(parents=True, exist_ok=True)
        nome_seguro = f"{int(time.time())}_{secure_filename(arquivo.filename)}"
        caminho = pasta / nome_seguro
        arquivo.save(caminho)

        try:
            tipo, linhas = atendimentos_model.processar_planilha(caminho)
            unidade_id = request.form.get("unidade_id", type=int)
            importacao_id = atendimentos_model.salvar_metricas(
                linhas,
                arquivo.filename,
                tipo,
                usuario_id=u["id"],
                usuario_nome=u["nome"],
                unidade_id=unidade_id,
            )
            _auditar(
                "importar", "atendimento_metricas", importacao_id,
                novo={
                    "arquivo": arquivo.filename,
                    "tipo": tipo,
                    "registros": len(linhas),
                    "historico_anterior_preservado": True,
                },
                unidade=unidades_model.buscar_unidade(unidade_id),
            )
            flash(f"Planilha processada: {len(linhas)} colaboradores/departamentos atualizados ({tipo}).", "sucesso")
        except Exception as e:
            flash(f"Nao foi possivel processar a planilha: {e}", "erro")
        return redirect(url_for("admin_atendimentos", setor=setor_selecionado))

    return render_template(
        "admin_atendimentos.html",
        metricas=atendimentos_model.listar_metricas_por_setor(setor_selecionado or None),
        resumo=atendimentos_model.indicadores_gerais(setor_selecionado or None),
        setores_indicadores=atendimentos_model.setores_disponiveis(),
        setor_selecionado=setor_selecionado,
        pode_gerenciar_atendimentos=pode_gerenciar,
        unidades=unidades_model.listar_unidades(apenas_ativas=True),
    )

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


# ── AUDITORIA E UNIDADES ──────────────────────────────────
@app.route("/admin/auditoria")
@admin_required
def admin_auditoria():
    modulo = request.args.get("modulo", "").strip()
    termo = request.args.get("q", "").strip()
    unidade_id = request.args.get("unidade_id", type=int)
    eventos = auditoria_model.listar_eventos(
        modulo=modulo or None,
        unidade_id=unidade_id,
        termo=termo or None,
        limite=500,
    )
    integridade_ok, falha_id = auditoria_model.verificar_integridade()
    return render_template(
        "admin_auditoria.html",
        eventos=eventos,
        modulos=auditoria_model.modulos_disponiveis(),
        modulo_selecionado=modulo,
        termo=termo,
        unidades=unidades_model.listar_unidades(),
        unidade_selecionada=unidade_id,
        integridade_ok=integridade_ok,
        falha_id=falha_id,
    )


@app.route("/admin/unidades", methods=["GET", "POST"])
@superadmin_required
def admin_unidades():
    if request.method == "POST":
        acao = request.form.get("acao", "")
        codigo = request.form.get("codigo", "").strip().upper()
        nome = request.form.get("nome", "").strip()
        cidade = request.form.get("cidade", "").strip()
        tipo = request.form.get("tipo", "filial")
        if tipo not in ("sede", "filial"):
            tipo = "filial"
        if not codigo or not nome:
            flash("Informe o código e o nome da unidade.", "erro")
            return redirect(url_for("admin_unidades"))
        try:
            if acao == "criar":
                unidade_id = unidades_model.criar_unidade(codigo, nome, cidade, tipo)
                nova = unidades_model.buscar_unidade(unidade_id)
                _auditar("criar", "unidades", unidade_id, novo=nova, unidade=nova)
                flash("Unidade criada sem alterar registros antigos.", "sucesso")
            elif acao == "atualizar":
                unidade_id = request.form.get("unidade_id", type=int)
                anterior = unidades_model.buscar_unidade(unidade_id)
                unidades_model.atualizar_unidade(
                    unidade_id, codigo, nome, cidade, tipo,
                    request.form.get("ativo") == "1",
                )
                nova = unidades_model.buscar_unidade(unidade_id)
                _auditar("atualizar", "unidades", unidade_id, anterior=anterior, novo=nova, unidade=nova)
                flash("Unidade atualizada.", "sucesso")
        except sqlite3.IntegrityError:
            flash("Já existe uma unidade com esse código.", "erro")
        return redirect(url_for("admin_unidades"))

    return render_template(
        "admin_unidades.html",
        unidades=unidades_model.listar_unidades(),
        vinculos=unidades_model.resumo_vinculos(),
    )

# ── HONEYPOT ──────────────────────────────────────────────
@app.route("/admin/honeypot")
@admin_required
def admin_honeypot():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    resumo_niveis = conn.execute(
        """
        SELECT nivel, COUNT(*) AS total
        FROM honeypot_tentativas
        GROUP BY nivel
        ORDER BY total DESC
        """
    ).fetchall()
    top_ips = conn.execute(
        """
        SELECT ip, pais, COUNT(*) AS total,
               MAX(criado_em) AS ultimo,
               GROUP_CONCAT(DISTINCT nivel) AS niveis
        FROM honeypot_tentativas
        GROUP BY ip, pais
        ORDER BY total DESC, ultimo DESC
        LIMIT 20
        """
    ).fetchall()
    top_rotas = conn.execute(
        """
        SELECT rota, COUNT(*) AS total
        FROM honeypot_tentativas
        GROUP BY rota
        ORDER BY total DESC
        LIMIT 12
        """
    ).fetchall()
    tentativas = conn.execute(
        """
        SELECT *
        FROM honeypot_tentativas
        ORDER BY id DESC
        LIMIT 300
        """
    ).fetchall()
    conn.close()
    return render_template(
        "admin_honeypot.html",
        resumo_niveis=resumo_niveis,
        top_ips=top_ips,
        top_rotas=top_rotas,
        tentativas=tentativas,
    )

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
            elif usuarios_model.buscar_usuario_por_email(email, incluir_excluido=True):
                flash("E-mail já cadastrado.", "erro")
            else:
                uid = usuarios_model.criar_usuario(nome, email, senha, role, setor)
                unidade_id = request.form.get("unidade_id", type=int)
                unidades_model.vincular_usuario(uid, unidade_id, usuario_atual()["id"])
                _auditar(
                    "criar", "usuarios", uid, novo=usuarios_model.buscar_usuario_por_id(uid),
                    unidade=unidades_model.buscar_unidade(unidade_id),
                )
                flash("Usuário criado.", "sucesso")
        elif acao == "atualizar_role":
            uid = request.form.get("usuario_id",type=int)
            anterior = usuarios_model.buscar_usuario_por_id(uid)
            usuarios_model.atualizar_role(uid, request.form.get("role"))
            _auditar("alterar_papel", "usuarios", uid, anterior=anterior, novo=usuarios_model.buscar_usuario_por_id(uid))
            flash("Papel atualizado.", "sucesso")
        elif acao == "atualizar":
            uid = request.form.get("usuario_id", type=int)
            nome = request.form.get("nome","").strip()
            email = request.form.get("email","").strip()
            role = request.form.get("role","comum")
            setor = request.form.get("setor","").strip()
            senha = request.form.get("senha","")
            existente = usuarios_model.buscar_usuario_por_email(email, incluir_excluido=True)
            atual = usuario_atual()
            if not nome or not email:
                flash("Preencha nome e e-mail.", "erro")
            elif role not in usuarios_model.PAPEIS:
                flash("Papel inválido.", "erro")
            elif atual and uid == atual["id"] and role != atual["role"]:
                flash("Você não pode alterar o próprio papel durante a sessão.", "erro")
            elif existente and existente["id"] != uid:
                flash("E-mail ja cadastrado em outro usuario.", "erro")
            else:
                anterior = usuarios_model.buscar_usuario_por_id(uid)
                usuarios_model.atualizar_usuario(uid, nome, email, role, setor, senha or None)
                unidade_id = request.form.get("unidade_id", type=int)
                unidades_model.vincular_usuario(uid, unidade_id, usuario_atual()["id"])
                _auditar(
                    "atualizar", "usuarios", uid, anterior=anterior,
                    novo=usuarios_model.buscar_usuario_por_id(uid),
                    unidade=unidades_model.buscar_unidade(unidade_id),
                    detalhes={"senha_alterada": bool(senha)},
                )
                flash("Usuario atualizado.", "sucesso")
        elif acao == "alternar_status":
            uid = request.form.get("usuario_id",type=int)
            anterior = usuarios_model.buscar_usuario_por_id(uid)
            novo_ativo = request.form.get("ativo")=="1"
            atual = usuario_atual()
            if atual and uid == atual["id"] and not novo_ativo:
                flash("Você não pode desativar o próprio usuário durante a sessão.", "erro")
            else:
                usuarios_model.atualizar_status(uid, novo_ativo)
                _auditar("alterar_status", "usuarios", uid, anterior=anterior, novo=usuarios_model.buscar_usuario_por_id(uid))
                flash("Status atualizado.", "sucesso")
        elif acao == "excluir":
            uid = request.form.get("usuario_id", type=int)
            atual = usuario_atual()
            if atual and uid == atual["id"]:
                flash("Voce nao pode excluir o proprio usuario logado.", "erro")
            else:
                anterior = usuarios_model.buscar_usuario_por_id(uid)
                usuarios_model.excluir_usuario(uid)
                _auditar(
                    "remover_logicamente", "usuarios", uid, anterior=anterior,
                    novo={"id": uid, "ativo": 0, "estado": "removido_logicamente"},
                    unidade=unidades_model.unidade_do_usuario(uid),
                )
                flash("Usuario removido.", "sucesso")
        return redirect(url_for("admin_usuarios"))
    return render_template("admin_usuarios.html",
                           usuarios=usuarios_model.listar_usuarios(),
                           papeis=usuarios_model.PAPEIS,
                           unidades=unidades_model.listar_unidades(apenas_ativas=True),
                           unidades_por_usuario=unidades_model.unidades_por_usuario())

# ── ERROS ────────────────────────────────────────────────
@app.errorhandler(404)
def e404(e): return render_template("erros/404.html"), 404
@app.errorhandler(500)
def e500(e): return render_template("erros/500.html"), 500

# ── STARTUP ──────────────────────────────────────────────
def inicializar_runtime():
    if app.config.get("AUTO_MIGRATE_ON_STARTUP", True):
        criar_tabelas()
        aplicar_migracoes(DB_PATH)
    else:
        app.logger.warning("AUTO_MIGRATE_ON_STARTUP=0: migracoes automaticas desativadas.")

    if app.config.get("BOOTSTRAP_SUPERADMIN_ON_STARTUP", True):
        bootstrap_superadmin()

    if app.config.get("LOAD_BLUEPRINTS_ON_STARTUP", True):
        carregar_apps()


inicializar_runtime()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "sim"}
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=debug and not app.config.get("IS_PRODUCTION", False),
    )
