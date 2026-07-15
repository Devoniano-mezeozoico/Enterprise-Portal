"""
Lógica de geração do TXT de importação RPA para autônomos.

Extraída do script desktop original (AutonomoRPA.py / Tkinter) e
adaptada para receber um arquivo em memória (upload via Flask) em vez
de um caminho selecionado em uma janela de diálogo.
"""

import datetime

import pandas as pd


def formatar_cpf(cpf) -> str:
    cpf = ''.join(filter(str.isdigit, str(cpf)))
    cpf = cpf.zfill(11)
    return (
        f"{cpf[:3]}."
        f"{cpf[3:6]}."
        f"{cpf[6:9]}-"
        f"{cpf[9:]}"
    )


def gerar_arquivo_txt(arquivo_excel):
    """
    Recebe um arquivo da planilha de contratos (caminho ou objeto tipo
    arquivo, como o FileStorage do Flask) e devolve uma tupla:
    (conteudo_txt: str, total_exportados: int).

    Lança ValueError se nenhum registro válido for encontrado.
    """
    df = pd.read_excel(arquivo_excel, header=7)

    linhas = []

    for _, row in df.iterrows():
        try:
            nome = str(row["RESPONSÁVEL PELO VEÍCULO"]).strip()

            cpf = ''.join(
                filter(str.isdigit, str(row["Nº  CNPJ/CPF"]))
            )

            nascimento = row["DATA NASCIMENTO"]

            if len(cpf) != 11:
                continue

            if pd.isna(nascimento):
                continue

            if isinstance(nascimento, (pd.Timestamp, datetime.datetime, datetime.date)):
                nascimento = nascimento.strftime("%d/%m/%Y")
            else:
                nascimento = str(nascimento).strip()

            cpf_formatado = formatar_cpf(cpf)

            linha = (
                f"{cpf_formatado};"
                f"{nome};"
                f";;;;;;;;;;;;;;"
                f"{nascimento};"
                f";;;;;;;;;;;;;;;;;;;;;;"
                f"7825-10;15;711;20;10;"
            )

            linhas.append(linha)

        except Exception:
            continue

    if not linhas:
        raise ValueError("Nenhum registro válido encontrado na planilha.")

    return "\n".join(linhas), len(linhas)
