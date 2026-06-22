# Portal Gumz — Intranet 2.0

Intranet corporativa em Flask: hub de aplicativos por setor, notícias,
agenda, reserva de salas, POPs e um assistente de IA integrado ao
Ollama.

## O que foi corrigido

O `app.py` original e os templates continham vários problemas que
impediam o sistema de funcionar corretamente. Foram corrigidos:

- **Imports faltando em `app.py`**: `socket`, `importlib`, `os` e
  `abort` eram usados mas nunca importados — o servidor quebrava no
  primeiro acesso (`/apps/<setor>`) ou no registro de acesso.
- **Rota `/api/ia` inexistente**: o template `ia.html` chamava
  `fetch("/api/ia")`, mas essa rota não existia em `app.py`. Foi
  criada, usando a função `perguntar_ia()` de `ai/ollama.py`.
- **Template `admin_acessos.html` ausente**: a rota
  `/admin/acessos` renderizava um template que não existia no
  projeto. Foi criado.
- **Formulário de reservas sem backend**: `reservas.html` enviava um
  `POST` para `/reservas`, mas a rota só aceitava `GET` (erro 405). A
  rota agora trata `GET` e `POST`, grava no banco, valida horários e
  evita conflitos de agenda na mesma sala.
- **Hub de Apps quebrado**: cada subpasta em `apps/` precisa expor
  `bp` (Blueprint) e `APP_INFO` no seu `__init__.py` para o
  `carregar_apps()` funcionar. Isso não estava implementado em
  `fiscal`, `rh`, `reservas` e `gerador_rpa` — foi adicionado em
  todos.
- **CSS incompleto**: as classes `.apps-grid`, `.card-app`,
  `.app-icon`, `.abrir-app` (usadas em `apps.html`) e o estilo de
  mensagens de sucesso/tabela de acessos não existiam em
  `style.css`. Foram adicionadas.
- **Erros de digitação nos templates**: link `href="#"` da IA no
  menu lateral, atributo `hrfe` (em vez de `href`) na home, e marcas
  de bloco de código (` ``` `) que tinham ficado soltas no meio do
  HTML de `base.html`.
- **Banco de dados**: `criar_tabelas()` só criava a tabela
  `acessos`. Agora também garante `salas` e `reservas` (com
  `CREATE TABLE IF NOT EXISTS`, sem apagar dados existentes) e
  semeia 4 salas padrão se a tabela estiver vazia.

## Estrutura do projeto

```
Portal_Gumz/
├── app.py
├── requirements.txt
├── .env
├── ai/
│   ├── __init__.py
│   ├── ollama.py        # função perguntar_ia() — fala com o servidor Ollama
│   ├── prompts.py        # prompt de sistema da IA Gumz
│   └── teste_ai.py       # script de teste manual (CLI)
├── database/
│   ├── intranet.db
│   ├── models/
│   │   ├── usuarios.py   # scaffold (tabela ainda não usada em produção)
│   │   ├── salas.py
│   │   └── reservas.py
│   └── scripts/
│       ├── criar_banco.py
│       └── console_db.py
├── apps/                 # cada setor é um Blueprint independente
│   ├── fiscal/
│   ├── rh/
│   ├── reservas/
│   └── gerador_rpa/
├── static/
│   ├── style.css
│   └── js/reservas.js
└── templates/
    ├── base.html, index.html, noticias.html, pops.html, ...
    └── erros/404.html, erros/500.html
```

## Como rodar

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# cria/atualiza o banco (opcional, app.py já faz isso na inicialização)
python database/scripts/criar_banco.py

flask run
# ou: python app.py
```

## IA Corporativa (Ollama)

O assistente em `/ia` depende de um servidor Ollama em execução. No
servidor, o pacote `ai/` deve conter `__init__.py`, `ollama.py`,
`prompts.py` e `teste_ai.py` (incluídos neste pacote). Para testar a
integração isoladamente, sem passar pelo Flask:

```bash
ollama serve            # em um terminal
ollama pull llama3      # baixa o modelo configurado em OLLAMA_MODEL

# em outro terminal, na raiz do projeto:
python -m ai.teste_ai "Qual o horário de funcionamento da empresa?"
```

As variáveis `OLLAMA_URL` e `OLLAMA_MODEL` (arquivo `.env`) permitem
apontar para outro host/modelo sem alterar código.

## Adicionando novos apps ao Hub

Para que um novo setor apareça no Hub de Apps, crie uma pasta em
`apps/<nome>/` com:

```python
# apps/<nome>/routes.py
from flask import Blueprint

bp = Blueprint("<nome>", __name__, url_prefix="/apps/<nome>")
APP_INFO = {
    "nome": "Nome exibido",
    "descricao": "Descrição curta",
    "icone": "fa-solid fa-icone",   # ou um emoji, ex.: "📄"
    "url": "/apps/<nome>/...",
    "setor": "Nome do Setor",
}
```

```python
# apps/<nome>/__init__.py
from .routes import bp, APP_INFO
__all__ = ["bp", "APP_INFO"]
```

`app.py` carrega essas pastas automaticamente ao iniciar.

## Observação sobre `static/img/`

Os arquivos `logo.png` e `favicon.ico` originais eram binários e não
puderam ser recuperados a partir do texto colado. Foram incluídos
placeholders simples — substitua por suas imagens reais quando
possível.
