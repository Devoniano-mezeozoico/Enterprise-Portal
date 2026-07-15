import os
import sqlite3
from datetime import datetime

DB_PATH = "database/honeypot.db"


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar():
    conn = _conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS fake_users(id INTEGER PRIMARY KEY AUTOINCREMENT,nome TEXT,email TEXT UNIQUE,role TEXT,status TEXT,ultimo_login TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fake_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT,titulo TEXT,cliente TEXT,prioridade TEXT,status TEXT,responsavel TEXT,criado_em TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fake_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,nivel TEXT,origem TEXT,mensagem TEXT,criado_em TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fake_backups(id INTEGER PRIMARY KEY AUTOINCREMENT,arquivo TEXT,tamanho TEXT,status TEXT,criado_em TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fake_telemetria(id INTEGER PRIMARY KEY AUTOINCREMENT,ip TEXT,user_agent TEXT,rota TEXT,acao TEXT,detalhe TEXT,criado_em TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("SELECT COUNT(*) FROM fake_users")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO fake_users(nome,email,role,status,ultimo_login) VALUES(?,?,?,?,?)", [
            ("Administrador Sistema", "admin@empresa.local", "superadmin", "ativo", "2026-06-30 07:41"),
            ("Suporte Interno", "suporte@empresa.local", "admin", "ativo", "2026-06-29 18:22"),
            ("Backup Service", "backup@empresa.local", "service", "ativo", "2026-06-30 02:00"),
            ("Auditoria", "auditoria@empresa.local", "viewer", "bloqueado", "2026-06-21 11:13"),
        ])
    c.execute("SELECT COUNT(*) FROM fake_tickets")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO fake_tickets(titulo,cliente,prioridade,status,responsavel,criado_em) VALUES(?,?,?,?,?,?)", [
            ("Falha ao sincronizar banco fiscal", "Sistema Fiscal", "alta", "em andamento", "Suporte Interno", "2026-06-30 08:10"),
            ("Revisar permissao de relatorios", "Controladoria", "media", "aberto", "Administrador Sistema", "2026-06-30 09:02"),
            ("Erro intermitente no exportador", "TI", "baixa", "aguardando", "Backup Service", "2026-06-29 16:44"),
        ])
    c.execute("SELECT COUNT(*) FROM fake_logs")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO fake_logs(nivel,origem,mensagem,criado_em) VALUES(?,?,?,?)", [
            ("WARN", "auth", "3 tentativas invalidas para admin@empresa.local", "2026-06-30 08:12"),
            ("INFO", "backup", "backup incremental finalizado", "2026-06-30 02:03"),
            ("ERROR", "database", "timeout em consulta legacy_reports", "2026-06-29 23:48"),
            ("INFO", "scheduler", "job sync_clients executado", "2026-06-29 22:10"),
        ])
    c.execute("SELECT COUNT(*) FROM fake_backups")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO fake_backups(arquivo,tamanho,status,criado_em) VALUES(?,?,?,?)", [
            ("intranet_full_2026-06-30.zip", "1.8 GB", "protegido", "2026-06-30 02:00"),
            ("usuarios_export_2026-06-29.csv", "248 KB", "protegido", "2026-06-29 19:30"),
            ("configs_legacy.tar.gz", "17 MB", "bloqueado", "2026-06-28 04:12"),
        ])
    conn.commit()
    conn.close()


def registrar(ip, user_agent, rota, acao, detalhe=""):
    inicializar()
    conn = _conn()
    conn.execute(
        "INSERT INTO fake_telemetria(ip,user_agent,rota,acao,detalhe,criado_em) VALUES(?,?,?,?,?,?)",
        (ip, user_agent, rota, acao, detalhe, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def dashboard():
    inicializar()
    conn = _conn()
    dados = {
        "usuarios": conn.execute("SELECT COUNT(*) AS total FROM fake_users").fetchone()["total"],
        "tickets": conn.execute("SELECT COUNT(*) AS total FROM fake_tickets").fetchone()["total"],
        "logs": conn.execute("SELECT COUNT(*) AS total FROM fake_logs").fetchone()["total"],
        "backups": conn.execute("SELECT COUNT(*) AS total FROM fake_backups").fetchone()["total"],
        "tickets_recentes": conn.execute("SELECT * FROM fake_tickets ORDER BY id DESC LIMIT 5").fetchall(),
        "logs_recentes": conn.execute("SELECT * FROM fake_logs ORDER BY id DESC LIMIT 5").fetchall(),
    }
    conn.close()
    return dados


def listar(tabela):
    inicializar()
    permitidas = {"users": "fake_users", "tickets": "fake_tickets", "logs": "fake_logs", "backups": "fake_backups", "telemetry": "fake_telemetria"}
    if tabela not in permitidas:
        return []
    conn = _conn()
    rows = conn.execute(f"SELECT * FROM {permitidas[tabela]} ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    return rows
