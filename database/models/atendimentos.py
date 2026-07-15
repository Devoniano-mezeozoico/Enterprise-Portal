import os
import re
import sqlite3
import unicodedata
from datetime import time, timedelta
from pathlib import Path

import pandas as pd
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH
UPLOADS_ATENDIMENTOS = Path("static/uploads/atendimentos")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _limpar_nome_coluna(coluna):
    return re.sub(r"\s+", " ", str(coluna or "")).strip().lower()


def _normalizar_texto(texto):
    texto = str(texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.replace("�", "")
    return re.sub(r"[^a-z0-9]+", "", texto)


def _area_canonica(texto):
    norm = _normalizar_texto(texto)
    for termo in ("departamento", "setor", "grupo", "responsavel", "conversa"):
        norm = norm.replace(termo, "")

    aliases = {
        "ti": {"ti", "tecnologiainformacao", "informatica", "suporte"},
        "fiscal": {"fiscal"},
        "contabil": {"contabil", "contabilidade"},
        "rh": {"rh", "recursoshumanos", "pessoal", "dp"},
        "societario": {"societario"},
        "consultoria": {"consultoria"},
        "gerencia": {"gerencia", "gernci", "gerncia"},
        "administrativo": {"administrativo", "administracao"},
        "comercial": {"comercial"},
    }
    for area, nomes in aliases.items():
        if norm in nomes:
            return area
    return norm


def _departamento_do_setor(departamento, setor):
    setor_norm = _area_canonica(setor)
    depto_norm = _area_canonica(departamento)
    if not setor_norm or not depto_norm:
        return False
    if setor_norm == depto_norm:
        return True
    if len(setor_norm) >= 3 and setor_norm in depto_norm:
        return True
    if len(depto_norm) >= 3 and depto_norm in setor_norm:
        return True
    return False


def _achar_coluna(colunas, candidatos):
    candidatos_norm = [_normalizar_texto(candidato) for candidato in candidatos]
    for col in colunas:
        nome = _limpar_nome_coluna(col)
        nome_norm = _normalizar_texto(col)
        if all(candidato in nome or candidato_norm in nome_norm for candidato, candidato_norm in zip(candidatos, candidatos_norm)):
            return col
    return None


def _achar_coluna_satisfeito(colunas):
    for col in colunas:
        norm = _normalizar_texto(col)
        if "satisf" not in norm or "pesquisa" in norm:
            continue
        if "insatisf" in norm or "nao" in norm or norm.startswith("no"):
            continue
        return col
    return None


def _achar_coluna_nao_satisfeito(colunas):
    for col in colunas:
        norm = _normalizar_texto(col)
        if "insatisf" in norm:
            return col
        if "satisf" in norm and ("nao" in norm or norm.startswith("no")):
            return col
    return None


def _segundos_para_hhmmss(segundos):
    segundos = int(round(float(segundos or 0)))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{seg:02d}"


def formatar_tempo(segundos):
    return _segundos_para_hhmmss(segundos)


def setor_e_gerencial(setor):
    setor_norm = _area_canonica(setor)
    return setor_norm == "gerencia" or "gerencia" in setor_norm or "gerncia" in setor_norm


def _valor_inteiro(valor):
    numero = pd.to_numeric(valor, errors="coerce")
    if pd.isna(numero):
        return 0
    return int(numero)


def _classificar_satisfacao(valor):
    norm = _normalizar_texto(valor)
    if not norm or norm in {"nan", "-"}:
        return None
    if "insatisfeito" in norm or "naosatisfeito" in norm or "nosatisfeito" in norm:
        return "nao_satisfeito"
    if norm == "satisfeito" or norm.startswith("satisfeito"):
        return "satisfeito"
    return None


def _percentual_satisfacao(satisfeitos, nao_satisfeitos):
    total = int(satisfeitos or 0) + int(nao_satisfeitos or 0)
    if total <= 0:
        return 0.0
    return round((int(satisfeitos or 0) / total) * 100, 2)


def _duracao_para_segundos(valor):
    if pd.isna(valor):
        return None
    if isinstance(valor, timedelta):
        return int(valor.total_seconds())
    if isinstance(valor, time):
        return valor.hour * 3600 + valor.minute * 60 + valor.second
    if isinstance(valor, (int, float)):
        if valor < 1:
            return int(round(valor * 24 * 3600))
        return int(round(valor))
    texto = str(valor).strip()
    if not texto or texto == "-":
        return None
    partes = texto.split(":")
    try:
        partes = [int(float(parte)) for parte in partes]
    except ValueError:
        return None
    if len(partes) == 3:
        return partes[0] * 3600 + partes[1] * 60 + partes[2]
    if len(partes) == 2:
        return partes[0] * 60 + partes[1]
    if len(partes) == 1:
        return partes[0]
    return None


def _processar_resultado_pronto(df):
    nome_col = _achar_coluna(df.columns, ["nome"]) or df.columns[0]
    depto_col = _achar_coluna(df.columns, ["departamento"])
    qtd_col = _achar_coluna(df.columns, ["qtd"]) or _achar_coluna(df.columns, ["atendimento"])
    tempo_col = _achar_coluna(df.columns, ["tempo"]) or _achar_coluna(df.columns, ["resposta"])
    satisfeito_col = _achar_coluna_satisfeito(df.columns)
    nao_satisfeito_col = _achar_coluna_nao_satisfeito(df.columns)
    if not depto_col or not qtd_col or not tempo_col:
        raise ValueError("Nao encontrei as colunas esperadas no resultado pronto.")
    linhas = []
    for _, row in df.iterrows():
        nome = str(row.get(nome_col, "")).strip()
        departamento = str(row.get(depto_col, "")).strip()
        qtd = pd.to_numeric(row.get(qtd_col), errors="coerce")
        segundos = _duracao_para_segundos(row.get(tempo_col))
        if not nome or nome.lower() == "nan" or pd.isna(qtd) or segundos is None:
            continue
        satisfeitos = _valor_inteiro(row.get(satisfeito_col)) if satisfeito_col else 0
        nao_satisfeitos = _valor_inteiro(row.get(nao_satisfeito_col)) if nao_satisfeito_col else 0
        linhas.append({
            "nome": nome,
            "departamento": departamento or "Sem departamento",
            "qtd_atendimentos": int(qtd),
            "tempo_medio_segundos": int(segundos),
            "tempo_medio_formatado": _segundos_para_hhmmss(segundos),
            "satisfeitos": satisfeitos,
            "nao_satisfeitos": nao_satisfeitos,
            "total_pesquisa": satisfeitos + nao_satisfeitos,
            "satisfacao_percentual": _percentual_satisfacao(satisfeitos, nao_satisfeitos),
        })
    return linhas


def _processar_bruto(df):
    responsavel_col = _achar_coluna(df.columns, ["respons"])
    departamento_col = _achar_coluna(df.columns, ["grupo", "respons"])
    tempo_col = _achar_coluna(df.columns, ["tempo", "espera"])
    satisfacao_col = _achar_coluna(df.columns, ["pesquisa", "satisf"]) or _achar_coluna(df.columns, ["satisf"])
    if not responsavel_col or not departamento_col or not tempo_col:
        raise ValueError("Nao encontrei as colunas Responsavel, Grupo responsavel e Tempo de espera.")
    colunas = [responsavel_col, departamento_col, tempo_col]
    if satisfacao_col:
        colunas.append(satisfacao_col)
    trabalho = df[colunas].copy()
    trabalho.columns = ["nome", "departamento", "tempo"] + (["satisfacao"] if satisfacao_col else [])
    trabalho["nome"] = trabalho["nome"].astype(str).str.strip()
    trabalho["departamento"] = trabalho["departamento"].astype(str).str.strip()
    trabalho["tempo_segundos"] = trabalho["tempo"].map(_duracao_para_segundos)
    if satisfacao_col:
        trabalho["satisfeito_flag"] = trabalho["satisfacao"].map(lambda valor: 1 if _classificar_satisfacao(valor) == "satisfeito" else 0)
        trabalho["nao_satisfeito_flag"] = trabalho["satisfacao"].map(lambda valor: 1 if _classificar_satisfacao(valor) == "nao_satisfeito" else 0)
    else:
        trabalho["satisfeito_flag"] = 0
        trabalho["nao_satisfeito_flag"] = 0
    trabalho = trabalho[(trabalho["nome"] != "") & (trabalho["nome"] != "-") & (trabalho["nome"].str.lower() != "nan") & trabalho["tempo_segundos"].notna()].copy()
    trabalho.loc[trabalho["departamento"].isin(["", "-", "nan", "NaN"]), "departamento"] = "Sem departamento"
    agrupado = trabalho.groupby(["nome", "departamento"], dropna=False).agg(
        qtd_atendimentos=("nome", "size"),
        tempo_medio_segundos=("tempo_segundos", "mean"),
        satisfeitos=("satisfeito_flag", "sum"),
        nao_satisfeitos=("nao_satisfeito_flag", "sum"),
    ).reset_index()
    agrupado["tempo_medio_segundos"] = agrupado["tempo_medio_segundos"].round().astype(int)
    agrupado["tempo_medio_formatado"] = agrupado["tempo_medio_segundos"].map(_segundos_para_hhmmss)
    agrupado["total_pesquisa"] = agrupado["satisfeitos"] + agrupado["nao_satisfeitos"]
    agrupado["satisfacao_percentual"] = agrupado.apply(
        lambda row: _percentual_satisfacao(row["satisfeitos"], row["nao_satisfeitos"]),
        axis=1,
    )
    agrupado = agrupado.sort_values(["tempo_medio_segundos", "qtd_atendimentos"], ascending=[False, False])
    return agrupado.to_dict("records")


def processar_planilha(caminho_arquivo):
    df = pd.read_excel(caminho_arquivo)
    colunas_norm = [_limpar_nome_coluna(c) for c in df.columns]
    parece_resultado = any("qtd" in c for c in colunas_norm) and any("tempo" in c for c in colunas_norm)
    linhas = _processar_resultado_pronto(df) if parece_resultado else _processar_bruto(df)
    tipo = "resultado" if parece_resultado else "bruto"
    if not linhas:
        raise ValueError("A planilha foi lida, mas nenhum atendimento valido foi encontrado.")
    return tipo, linhas


def salvar_metricas(linhas, arquivo_origem, tipo_origem, usuario_id=None, usuario_nome=None, unidade_id=None):
    conn = _conn()
    garantir_schema(conn)
    try:
        conn.execute("BEGIN IMMEDIATE")
        anteriores = conn.execute("SELECT COUNT(*) FROM atendimento_metricas").fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO atendimento_importacoes(
                arquivo_origem, tipo_origem, usuario_id, usuario_nome, unidade_id,
                registros_anteriores, registros_novos
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                arquivo_origem,
                tipo_origem,
                usuario_id,
                usuario_nome,
                unidade_id,
                anteriores,
                len(linhas),
            ),
        )
        importacao_id = cur.lastrowid
        if anteriores:
            conn.execute(
                """
                INSERT INTO atendimento_metricas_historico(
                    importacao_id, registro_original_id, nome, departamento,
                    qtd_atendimentos, tempo_medio_segundos, tempo_medio_formatado,
                    satisfeitos, nao_satisfeitos, total_pesquisa, satisfacao_percentual,
                    arquivo_origem, tipo_origem, atualizado_em
                )
                SELECT ?, id, nome, departamento, qtd_atendimentos,
                       tempo_medio_segundos, tempo_medio_formatado,
                       satisfeitos, nao_satisfeitos, total_pesquisa,
                       satisfacao_percentual, arquivo_origem, tipo_origem, atualizado_em
                FROM atendimento_metricas
                """,
                (importacao_id,),
            )
        conn.execute("DELETE FROM atendimento_metricas")
        for linha in linhas:
            conn.execute(
                """INSERT INTO atendimento_metricas(
                       nome,departamento,qtd_atendimentos,tempo_medio_segundos,tempo_medio_formatado,
                       satisfeitos,nao_satisfeitos,total_pesquisa,satisfacao_percentual,
                       arquivo_origem,tipo_origem)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    linha["nome"],
                    linha["departamento"],
                    linha["qtd_atendimentos"],
                    linha["tempo_medio_segundos"],
                    linha["tempo_medio_formatado"],
                    int(linha.get("satisfeitos") or 0),
                    int(linha.get("nao_satisfeitos") or 0),
                    int(linha.get("total_pesquisa") or 0),
                    float(linha.get("satisfacao_percentual") or 0),
                    arquivo_origem,
                    tipo_origem,
                ),
            )
        conn.commit()
        return importacao_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def garantir_schema(conn=None):
    fechar = False
    if conn is None:
        conn = _conn()
        fechar = True
    colunas = {row["name"] for row in conn.execute("PRAGMA table_info(atendimento_metricas)").fetchall()}
    novas_colunas = {
        "satisfeitos": "INTEGER NOT NULL DEFAULT 0",
        "nao_satisfeitos": "INTEGER NOT NULL DEFAULT 0",
        "total_pesquisa": "INTEGER NOT NULL DEFAULT 0",
        "satisfacao_percentual": "REAL NOT NULL DEFAULT 0",
    }
    for coluna, definicao in novas_colunas.items():
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE atendimento_metricas ADD COLUMN {coluna} {definicao}")
    conn.commit()
    if fechar:
        conn.close()


def listar_metricas():
    conn = _conn()
    rows = conn.execute("SELECT * FROM atendimento_metricas ORDER BY qtd_atendimentos DESC, tempo_medio_segundos DESC, nome").fetchall()
    conn.close()
    return rows


def _where_setor(setor):
    setor = str(setor or "").strip()
    if not setor:
        return "", ()
    return "WHERE lower(COALESCE(departamento, '')) = lower(?)", (setor,)


def _filtrar_por_setor(rows, setor):
    setor = str(setor or "").strip()
    if not setor:
        return list(rows)
    return [row for row in rows if _departamento_do_setor(row["departamento"], setor)]


def listar_metricas_por_setor(setor=None):
    rows = listar_metricas()
    if setor:
        return _filtrar_por_setor(rows, setor)
    return rows


def setores_disponiveis():
    conn = _conn()
    rows = conn.execute(
        """
        SELECT DISTINCT COALESCE(NULLIF(TRIM(departamento), ''), 'Sem departamento') AS departamento
        FROM atendimento_metricas
        ORDER BY departamento
        """
    ).fetchall()
    conn.close()
    return [row["departamento"] for row in rows]


def _comparativo_neutro(texto="Sem periodo anterior"):
    return {
        "direcao": "neutral",
        "icone": "fa-solid fa-minus",
        "texto": texto,
        "valor": None,
    }


def _row_int(row, campo):
    try:
        return int(row[campo] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 0


def _row_float(row, campo):
    try:
        return float(row[campo] or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 0.0


def _resumo_linhas(rows):
    rows = list(rows)
    total = sum(_row_int(row, "qtd_atendimentos") for row in rows)
    tempo_ponderado = sum(_row_int(row, "tempo_medio_segundos") * _row_int(row, "qtd_atendimentos") for row in rows)
    satisfeitos = sum(_row_int(row, "satisfeitos") for row in rows)
    nao_satisfeitos = sum(_row_int(row, "nao_satisfeitos") for row in rows)
    total_pesquisa = satisfeitos + nao_satisfeitos
    tempo_medio = int(round(tempo_ponderado / total)) if total else 0
    satisfacao_percentual = _percentual_satisfacao(satisfeitos, nao_satisfeitos)
    return {
        "pessoas": len(rows),
        "total": total,
        "tempo_medio_segundos": tempo_medio,
        "tempo_medio_formatado": _segundos_para_hhmmss(tempo_medio),
        "satisfeitos": satisfeitos,
        "nao_satisfeitos": nao_satisfeitos,
        "total_pesquisa": total_pesquisa,
        "satisfacao": satisfacao_percentual if total_pesquisa else None,
        "satisfacao_percentual": satisfacao_percentual,
        "satisfacao_texto": f"{satisfacao_percentual:.1f}% satisfeitos" if total_pesquisa else "Sem respostas",
    }


def _comparar(atual, anterior, unidade="", maior_melhor=True, casas=1):
    if anterior is None or anterior == 0:
        return _comparativo_neutro()
    diferenca = atual - anterior
    if abs(diferenca) < 0.0001:
        return {
            "direcao": "neutral",
            "icone": "fa-solid fa-minus",
            "texto": "Igual ao periodo anterior",
            "valor": 0,
        }
    variacao = (diferenca / anterior) * 100
    melhorou = diferenca > 0 if maior_melhor else diferenca < 0
    return {
        "direcao": "good" if melhorou else "bad",
        "icone": "fa-solid fa-arrow-up" if diferenca > 0 else "fa-solid fa-arrow-down",
        "texto": f"{variacao:+.{casas}f}% vs periodo anterior",
        "valor": round(diferenca, 2),
        "unidade": unidade,
    }


def _prefixo_upload(path):
    match = re.match(r"(\d+)_", path.name)
    if match:
        return int(match.group(1))
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def _arquivo_upload_atual(ultima):
    if not ultima:
        return None
    origem = str(ultima["arquivo_origem"] or "").strip()
    if not origem or not UPLOADS_ATENDIMENTOS.exists():
        return None
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", origem)
    candidatos = []
    for arquivo in UPLOADS_ATENDIMENTOS.glob("*.xls*"):
        if arquivo.name == origem or arquivo.name.endswith(f"_{origem}") or arquivo.name.endswith(f"_{seguro}"):
            candidatos.append(arquivo)
    if not candidatos:
        return None
    return sorted(candidatos, key=_prefixo_upload, reverse=True)[0]


def _linhas_periodo_anterior(ultima):
    if not UPLOADS_ATENDIMENTOS.exists():
        return []
    atual = _arquivo_upload_atual(ultima)
    atual_prefixo = _prefixo_upload(atual) if atual else None
    tipo_atual = str(ultima["tipo_origem"] or "") if ultima else ""
    arquivos = sorted(UPLOADS_ATENDIMENTOS.glob("*.xls*"), key=_prefixo_upload, reverse=True)
    for arquivo in arquivos:
        if atual and arquivo.resolve() == atual.resolve():
            continue
        if atual_prefixo is not None and _prefixo_upload(arquivo) >= atual_prefixo:
            continue
        try:
            tipo, linhas = processar_planilha(arquivo)
        except Exception:
            continue
        if tipo_atual and tipo != tipo_atual:
            continue
        return linhas
    return []


def indicadores_gerais(setor=None):
    rows = listar_metricas_por_setor(setor)
    ultima = sorted(rows, key=lambda row: row["atualizado_em"] or "", reverse=True)
    ultima = ultima[0] if ultima else None
    resumo_atual = _resumo_linhas(rows)
    anteriores = _linhas_periodo_anterior(ultima)
    if setor:
        anteriores = _filtrar_por_setor(anteriores, setor)
    resumo_anterior = _resumo_linhas(anteriores) if anteriores else None

    comparativos = {
        "qtd": _comparativo_neutro(),
        "tempo": _comparativo_neutro(),
        "satisfacao": _comparativo_neutro("Sem base de satisfacao"),
    }
    if resumo_anterior:
        comparativos = {
            "qtd": _comparar(resumo_atual["total"], resumo_anterior["total"], maior_melhor=True),
            "tempo": _comparar(resumo_atual["tempo_medio_segundos"], resumo_anterior["tempo_medio_segundos"], maior_melhor=False),
            "satisfacao": _comparar(
                resumo_atual["satisfacao_percentual"],
                resumo_anterior["satisfacao_percentual"] if resumo_anterior["total_pesquisa"] else None,
                maior_melhor=True,
            ),
        }

    resumo_atual.update({
        "setor": setor or "Todos os setores",
        "ultima": ultima,
        "comparativos": comparativos,
        "periodo_anterior": resumo_anterior,
    })
    return resumo_atual


def top_qtd(limite=10, setor=None):
    conn = _conn()
    if setor:
        todos = conn.execute("SELECT * FROM atendimento_metricas").fetchall()
        rows = sorted(
            _filtrar_por_setor(todos, setor),
            key=lambda row: (row["qtd_atendimentos"], row["tempo_medio_segundos"]),
            reverse=True,
        )[:limite]
    else:
        rows = conn.execute(
            "SELECT * FROM atendimento_metricas ORDER BY qtd_atendimentos DESC, tempo_medio_segundos DESC LIMIT ?",
            (limite,),
        ).fetchall()
    conn.close()
    return rows


def top_tempo(limite=10, setor=None):
    conn = _conn()
    if setor:
        todos = conn.execute("SELECT * FROM atendimento_metricas WHERE qtd_atendimentos > 0").fetchall()
        rows = sorted(
            _filtrar_por_setor(todos, setor),
            key=lambda row: (row["tempo_medio_segundos"], row["qtd_atendimentos"]),
            reverse=True,
        )[:limite]
    else:
        rows = conn.execute(
            "SELECT * FROM atendimento_metricas WHERE qtd_atendimentos > 0 ORDER BY tempo_medio_segundos DESC, qtd_atendimentos DESC LIMIT ?",
            (limite,),
        ).fetchall()
    conn.close()
    return rows


def resumo(setor=None):
    conn = _conn()
    if setor:
        rows = _filtrar_por_setor(
            conn.execute("SELECT * FROM atendimento_metricas").fetchall(),
            setor,
        )
        pessoas = len(rows)
        total = sum(row["qtd_atendimentos"] or 0 for row in rows)
        ultima = sorted(rows, key=lambda row: row["atualizado_em"] or "", reverse=True)
        ultima = ultima[0] if ultima else None
        conn.close()
        return {"pessoas": pessoas, "total": total, "ultima": ultima}
    row = conn.execute("SELECT COUNT(*) AS pessoas, COALESCE(SUM(qtd_atendimentos), 0) AS total FROM atendimento_metricas").fetchone()
    ultima = conn.execute("SELECT arquivo_origem, tipo_origem, atualizado_em FROM atendimento_metricas ORDER BY atualizado_em DESC LIMIT 1").fetchone()
    conn.close()
    return {"pessoas": row["pessoas"], "total": row["total"], "ultima": ultima}
