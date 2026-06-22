"""
Integração com o Ollama (modelo de IA local).

A função perguntar_ia() é usada pela rota /api/ia em app.py para
enviar a pergunta do usuário ao servidor Ollama e devolver a resposta.
"""

import os

import requests

from ai.prompts import montar_prompt

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
TIMEOUT_SEGUNDOS = 60


def perguntar_ia(pergunta: str, contexto_pops=None, contexto_noticias=None, contexto_eventos=None) -> str:
    """
    Envia uma pergunta para o Ollama (com o contexto relevante de
    POPs/notícias/agenda já embutido no prompt) e retorna a resposta
    em texto.

    Lança ValueError se a pergunta estiver vazia e
    requests.RequestException se o servidor Ollama não responder.
    """
    pergunta = (pergunta or "").strip()
    if not pergunta:
        raise ValueError("A pergunta não pode estar vazia.")

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": montar_prompt(pergunta, contexto_pops, contexto_noticias, contexto_eventos),
        "stream": False,
    }

    resposta = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=TIMEOUT_SEGUNDOS
    )
    resposta.raise_for_status()

    dados = resposta.json()
    return dados.get("response", "").strip()
