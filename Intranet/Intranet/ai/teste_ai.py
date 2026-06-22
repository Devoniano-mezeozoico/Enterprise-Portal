"""
Script de teste manual da integração com o Ollama.

Uso (a partir da raiz do projeto, com o virtualenv ativo):

    python -m ai.teste_ai "Qual o horário de funcionamento da empresa?"

Ou, sem argumentos, ele faz uma pergunta padrão de teste.
"""

import sys

from ai.ollama import perguntar_ia


def main():
    pergunta = " ".join(sys.argv[1:]) or "Olá, você está funcionando?"

    print(f"Pergunta: {pergunta}")
    print("Consultando o Ollama...")

    try:
        resposta = perguntar_ia(pergunta)
        print("\nResposta da IA:")
        print(resposta)
    except Exception as erro:
        print(f"\nErro ao consultar a IA: {erro}")
        print(
            "Verifique se o Ollama está em execução "
            "(ex.: 'ollama serve') e se o modelo configurado "
            "em OLLAMA_MODEL foi baixado (ex.: 'ollama pull llama3')."
        )


if __name__ == "__main__":
    main()
