"""
Prompts utilizados pela IA Corporativa Gumz.
"""

SYSTEM_PROMPT = """\
Você é a IA assistente, assistente virtual corporativo da enterprise Integrações.
Responda sempre em português do Brasil, de forma clara, objetiva e
profissional, em texto corrido (não em bloco de código, a menos que a
pergunta seja especificamente sobre programação). Quando não tiver
certeza de uma informação interna da empresa, avise o usuário que essa
informação ainda não está disponível para consulta automática e
recomende falar com o setor responsável.
"""


def _bloco_pops(contexto_pops):
    trechos = [
        f"### POP: {pop['titulo']}\n{(pop['conteudo_texto'] or '')[:1200]}"
        for pop in contexto_pops
    ]
    return "POPs internos relacionados:\n\n" + "\n\n".join(trechos)


def _bloco_noticias(contexto_noticias):
    trechos = [
        f"### Notícia: {noticia['titulo']}\n{(noticia['resumo'] or noticia['conteudo'] or '')[:800]}"
        for noticia in contexto_noticias
    ]
    return "Notícias internas relacionadas:\n\n" + "\n\n".join(trechos)


def _bloco_eventos(contexto_eventos):
    trechos = [
        f"### Evento: {evento['titulo']} — {evento['data_evento']} ({evento['setor']})\n"
        f"{evento['descricao'] or ''}"
        for evento in contexto_eventos
    ]
    return "Eventos de agenda relacionados:\n\n" + "\n\n".join(trechos)


def montar_prompt(pergunta, contexto_pops=None, contexto_noticias=None, contexto_eventos=None):
    """
    Combina o prompt de sistema com trechos de POPs, notícias e/ou
    eventos de agenda relevantes (encontrados por busca por palavras
    antes da chamada ao Ollama) e a pergunta do usuário.
    """
    pergunta = (pergunta or "").strip()

    blocos = []
    if contexto_pops:
        blocos.append(_bloco_pops(contexto_pops))
    if contexto_noticias:
        blocos.append(_bloco_noticias(contexto_noticias))
    if contexto_eventos:
        blocos.append(_bloco_eventos(contexto_eventos))

    bloco_contexto = ""
    if blocos:
        bloco_contexto = (
            "\n\nUse as informações abaixo como referência para "
            "responder, se forem relevantes. Não invente informações "
            "que não estão aqui:\n\n" + "\n\n---\n\n".join(blocos)
        )

    return f"{SYSTEM_PROMPT}{bloco_contexto}\n\nPergunta do usuário: {pergunta}\nResposta:"
