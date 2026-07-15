import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"

DEFAULTS = {
    "APP_NAME": "Portal Corporativo",
    "COMPANY_NAME": "Sua Empresa",
    "PORTAL_SUBTITLE": "Intranet 2.0",
    "AI_ASSISTANT_NAME": "IA Corporativa",
    "DEFAULT_ADMIN_EMAIL": "admin@empresa.local",
}


def _base_lines():
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    if ENV_EXAMPLE_PATH.exists():
        return ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    return []


def _upsert(lines, chave, valor):
    prefixo = f"{chave}="
    for indice, linha in enumerate(lines):
        if linha.startswith(prefixo):
            lines[indice] = f"{chave}={valor}"
            return
    lines.append(f"{chave}={valor}")


def main():
    parser = argparse.ArgumentParser(
        description="Personaliza os nomes basicos do portal sem alterar codigo."
    )
    parser.add_argument("--app-name", help="Nome exibido no portal.")
    parser.add_argument("--company-name", help="Nome da empresa, cliente ou pessoa.")
    parser.add_argument("--subtitle", help="Subtitulo exibido abaixo do nome.")
    parser.add_argument("--ai-name", help="Nome da assistente de IA.")
    parser.add_argument("--admin-email", help="E-mail inicial do superadmin.")
    args = parser.parse_args()

    valores = {
        "APP_NAME": args.app_name,
        "COMPANY_NAME": args.company_name,
        "PORTAL_SUBTITLE": args.subtitle,
        "AI_ASSISTANT_NAME": args.ai_name,
        "DEFAULT_ADMIN_EMAIL": args.admin_email,
    }

    linhas = _base_lines()
    for chave, padrao in DEFAULTS.items():
        _upsert(linhas, chave, valores[chave] or padrao)

    ENV_PATH.write_text("\n".join(linhas).rstrip() + "\n", encoding="utf-8")
    print(f"Configuracao salva em: {ENV_PATH}")


if __name__ == "__main__":
    main()
