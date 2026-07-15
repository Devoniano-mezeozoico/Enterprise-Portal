"""
Lógica de negócio do Gerador de RPA.

Mantida separada de routes.py para facilitar testes e reaproveitamento
por outras partes do sistema, se necessário.
"""


def gerar_script_rpa(nome_processo: str, passos: list[str]) -> str:
    """
    Gera um script Python de automação (RPA) simples a partir de uma
    lista de passos descritos em texto.
    """
    nome_processo = (nome_processo or "processo_rpa").strip() or "processo_rpa"
    passos = [p.strip() for p in (passos or []) if p and p.strip()]

    linhas = [
        f'"""',
        f"Script RPA gerado automaticamente: {nome_processo}",
        f'"""',
        "",
        "def executar():",
    ]

    if not passos:
        linhas.append("    pass  # Nenhum passo informado")
    else:
        for indice, passo in enumerate(passos, start=1):
            linhas.append(f"    # Passo {indice}: {passo}")
            linhas.append("    pass")

    linhas += [
        "",
        "",
        'if __name__ == "__main__":',
        "    executar()",
    ]

    return "\n".join(linhas)
