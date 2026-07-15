import os
import secrets


class ConfigError(RuntimeError):
    """Erro de configuração que deve impedir uso inseguro em produção."""


def env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "yes", "sim", "on"}


def env_text(nome, padrao):
    valor = os.environ.get(nome)
    if valor is None or not valor.strip():
        return padrao
    return valor.strip()


class AppConfig:
    APP_ENV = os.environ.get("APP_ENV", os.environ.get("FLASK_ENV", "development")).strip().lower()
    IS_PRODUCTION = APP_ENV in {"prod", "production", "producao", "produção"}

    APP_NAME = env_text("APP_NAME", "Portal Corporativo")
    COMPANY_NAME = env_text("COMPANY_NAME", "Sua Empresa")
    PORTAL_SUBTITLE = env_text("PORTAL_SUBTITLE", "Intranet 2.0")
    AI_ASSISTANT_NAME = env_text("AI_ASSISTANT_NAME", "IA Corporativa")
    DEFAULT_ADMIN_EMAIL = env_text("DEFAULT_ADMIN_EMAIL", "admin@empresa.local")

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SECRET_KEY_IS_TEMPORARY = False
    if not SECRET_KEY:
        if IS_PRODUCTION:
            raise ConfigError(
                f"Defina SECRET_KEY no ambiente antes de iniciar o {APP_NAME} em producao."
            )
        SECRET_KEY = secrets.token_urlsafe(48)
        SECRET_KEY_IS_TEMPORARY = True

    DB_PATH = os.environ.get("DATABASE_PATH", "database/intranet.db")
    LOG_DIR = os.environ.get("LOG_DIR", "logs")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024
    AUTO_MIGRATE_ON_STARTUP = env_bool("AUTO_MIGRATE_ON_STARTUP", True)
    BOOTSTRAP_SUPERADMIN_ON_STARTUP = env_bool("BOOTSTRAP_SUPERADMIN_ON_STARTUP", True)
    LOAD_BLUEPRINTS_ON_STARTUP = env_bool("LOAD_BLUEPRINTS_ON_STARTUP", True)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)

    WTF_CSRF_ENABLED = env_bool("CSRF_ENABLED", True)
    CSRF_EXEMPT_ENDPOINTS = {
        "static",
        "portal_notifications_sw",
        # O login falso precisa aceitar tentativas sem sessão para cumprir
        # sua função defensiva de honeypot. Ele nunca autentica no portal real.
        "admin_painel",
        "honeypot_database",
    }
    CSRF_EXEMPT_PREFIXES = (
        "/portal-notifications-sw.js",
    )
