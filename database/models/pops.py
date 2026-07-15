"""
Funções de acesso à tabela 'pops' e busca de relevância simples
(usada tanto na página de busca quanto pela IA, para encontrar POPs
relacionados à pergunta do usuário antes de consultar o Ollama).
"""

import os
import re
import sqlite3
from database.connection import DYNAMIC_DATABASE_PATH

DB_PATH = DYNAMIC_DATABASE_PATH


# ==================================================
# CRUD
# ==================================================
def listar_pops(busca=None, categoria=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = "SELECT id, titulo, categoria, nome_arquivo, criado_em FROM pops"
    condicoes = ["excluido_em IS NULL"]
    parametros = []

    if busca:
        condicoes.append("(titulo LIKE ? OR conteudo_texto LIKE ?)")
        termo = f"%{busca}%"
        parametros += [termo, termo]

    if categoria:
        condicoes.append("categoria = ?")
        parametros.append(categoria)

    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)

    sql += " ORDER BY criado_em DESC"

    cursor.execute(sql, parametros)
    pops = cursor.fetchall()
    conn.close()
    return pops


def listar_categorias():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT categoria FROM pops WHERE categoria IS NOT NULL AND excluido_em IS NULL ORDER BY categoria"
    )
    categorias = [linha[0] for linha in cursor.fetchall()]
    conn.close()
    return categorias


def contar_pops():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pops WHERE excluido_em IS NULL")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def buscar_pop_por_id(pop_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pops WHERE id = ? AND excluido_em IS NULL", (pop_id,))
    pop = cursor.fetchone()
    conn.close()
    return pop


def criar_pop(titulo, categoria, nome_arquivo, caminho_arquivo, conteudo_texto):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pops
            (titulo, categoria, nome_arquivo, caminho_arquivo, conteudo_texto)
        VALUES (?, ?, ?, ?, ?)
        """,
        (titulo, categoria, nome_arquivo, caminho_arquivo, conteudo_texto)
    )
    conn.commit()
    pop_id = cursor.lastrowid
    conn.close()
    return pop_id


def excluir_pop(pop_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE pops SET excluido_em=CURRENT_TIMESTAMP WHERE id = ? AND excluido_em IS NULL", (pop_id,))
    conn.commit()
    conn.close()


# ==================================================
# EXTRAÇÃO DE TEXTO (PDF / DOCX / TXT)
# ==================================================
def extrair_texto(caminho_arquivo, extensao):
    """
    Extrai o texto de um POP recém enviado, para permitir busca e uso
    pela IA. Retorna string vazia se não conseguir extrair (o POP
    continua sendo salvo e disponível para download mesmo assim).
    """
    extensao = extensao.lower()

    try:
        if extensao == ".txt":
            with open(caminho_arquivo, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        if extensao == ".pdf":
            from pypdf import PdfReader
            leitor = PdfReader(str(caminho_arquivo))
            paginas = [(pagina.extract_text() or "") for pagina in leitor.pages]
            return "\n".join(paginas)

        if extensao == ".docx":
            import docx
            documento = docx.Document(str(caminho_arquivo))
            paragrafos = [p.text for p in documento.paragraphs]
            return "\n".join(paragrafos)

    except Exception:
        return ""

    return ""


# ==================================================
# BUSCA DE RELEVÂNCIA (usada pela IA)
# ==================================================
def _tokenizar(texto):
    texto = (texto or "").lower()
    return set(re.findall(r"[a-zà-ÿ0-9]{3,}", texto))


def buscar_pops_relevantes(pergunta, limite=3):
    """
    Busca simples por sobreposição de palavras entre a pergunta e o
    título/conteúdo de cada POP. Não é uma busca semântica (não usa
    embeddings), mas é suficiente para uma biblioteca de POPs de
    tamanho corporativo típico (dezenas a poucas centenas de
    documentos) sem precisar de infraestrutura extra.
    """
    termos = _tokenizar(pergunta)
    if not termos:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pops WHERE excluido_em IS NULL")
    pops = cursor.fetchall()
    conn.close()

    pontuados = []
    for pop in pops:
        texto_pop = f"{pop['titulo']} {pop['conteudo_texto'] or ''}".lower()
        pontos = sum(1 for termo in termos if termo in texto_pop)
        if pontos > 0:
            pontuados.append((pontos, pop))

    pontuados.sort(key=lambda item: item[0], reverse=True)
    return [pop for _, pop in pontuados[:limite]]
