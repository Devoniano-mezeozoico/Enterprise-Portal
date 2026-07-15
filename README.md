# Portal Corporativo

Portal Corporativo é uma intranet interna em Flask para centralizar comunicados, notícias, POPs, agenda, reservas, apps internos, chamados de TI, indicadores, chat, auditoria e ferramentas administrativas.

O projeto é genérico: não depende de nome de cliente, cidade ou empresa no código. A personalização fica no arquivo `.env` ou no script `scripts/personalizar_portal.py`.

## Funcionalidades

- Autenticação por e-mail e senha.
- Perfis `comum`, `recepcao`, `admin` e `superadmin`.
- Comunicados com notificações e popup.
- Notícias internas com anexos.
- Biblioteca de POPs.
- Agenda, reservas de salas e eventos internos.
- Hub de apps por setor.
- Chat interno.
- Chamados e estoque de TI.
- Indicadores de atendimento por planilha.
- IA corporativa opcional via Ollama.
- Auditoria append-only para ações administrativas.
- Honeypot defensivo para rotas administrativas falsas.

## Tecnologias

- Python
- Flask
- SQLite
- Jinja2
- Pandas
- OpenPyXL
- xlrd
- pypdf
- python-docx
- pdfplumber
- Font Awesome
- Ollama, opcional para IA

## Instalação Rápida

Entre na raiz do projeto, a pasta onde ficam `app.py` e `requirements.txt`.

No Windows:

```powershell
cd Portal_Corporativo
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

No Linux/macOS:

```bash
cd Portal_Corporativo
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://127.0.0.1:5000/login
```

Importante: rode os comandos a partir da raiz do projeto. Se você estiver dentro de `scripts/`, `pip install -r requirements.txt` não vai encontrar o arquivo.

## Configuração

Crie um arquivo `.env` na raiz do projeto. Você pode começar copiando o exemplo:

```powershell
copy .env.example .env
```

Exemplo:

```env
APP_ENV=development
APP_NAME=Portal Corporativo
COMPANY_NAME=Sua Empresa
PORTAL_SUBTITLE=Intranet 2.0
AI_ASSISTANT_NAME=IA Corporativa
DEFAULT_ADMIN_EMAIL=admin@empresa.local

SECRET_KEY=troque-por-uma-chave-forte
DATABASE_PATH=database/intranet.db
LOG_DIR=logs
MAX_UPLOAD_MB=50

AUTO_MIGRATE_ON_STARTUP=1
BOOTSTRAP_SUPERADMIN_ON_STARTUP=1
LOAD_BLUEPRINTS_ON_STARTUP=1

SESSION_COOKIE_SECURE=0
SESSION_COOKIE_SAMESITE=Lax
CSRF_ENABLED=1

ADF_URL=
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3
```

Variáveis principais:

| Variável | Descrição |
| --- | --- |
| `APP_NAME` | Nome exibido no portal. |
| `COMPANY_NAME` | Nome da empresa, cliente ou pessoa. |
| `PORTAL_SUBTITLE` | Subtítulo exibido abaixo do nome do portal. |
| `AI_ASSISTANT_NAME` | Nome exibido para a assistente de IA. |
| `DEFAULT_ADMIN_EMAIL` | E-mail usado para criar o primeiro superadmin. |
| `SECRET_KEY` | Chave do Flask para sessões. Use uma chave forte em produção. |
| `DATABASE_PATH` | Caminho do SQLite. Caminhos relativos partem da raiz do projeto. |
| `AUTO_MIGRATE_ON_STARTUP` | Use `1` no primeiro boot para criar/atualizar tabelas. |
| `BOOTSTRAP_SUPERADMIN_ON_STARTUP` | Cria um superadmin temporário se o banco estiver sem usuários. |
| `OLLAMA_URL` e `OLLAMA_MODEL` | Configuração da IA local via Ollama. |

## Personalização

Você pode editar o `.env` manualmente ou usar:

```powershell
python scripts\personalizar_portal.py --app-name "Portal da Empresa" --company-name "Empresa" --admin-email "admin@empresa.com"
```

Isso atualiza as variáveis básicas sem alterar o código.

## Primeiro Acesso

No primeiro boot, se o banco estiver vazio, o sistema cria um superadmin temporário.

O e-mail vem de `DEFAULT_ADMIN_EMAIL`. A senha temporária aparece no log:

```powershell
Get-Content logs\app.log | Select-String "Senha"
```

Depois de entrar, crie uma conta definitiva ou redefina a senha conforme sua política interna.

Para listar admins ou redefinir senha:

```powershell
python scripts\reset_admin_password.py --listar
python scripts\reset_admin_password.py admin@empresa.local --gerar
```

## Banco de Dados

O projeto usa SQLite.

Por padrão, o banco fica em:

```text
database/intranet.db
```

Com `AUTO_MIGRATE_ON_STARTUP=1`, `python app.py` cria as tabelas automaticamente no primeiro uso.

Para aplicar migrações com backup verificado:

```powershell
python scripts\migrate_database.py
```

Esse script cria uma cópia de segurança antes de alterar a estrutura.

## IA com Ollama

A IA é opcional. Para usar:

```bash
ollama serve
ollama pull llama3
```

Depois confira no `.env`:

```env
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3
```

Teste manual:

```powershell
python -m ai.teste_ai "Quais POPs existem?"
```

## Estrutura

```text
Portal_Corporativo/
├── app.py
├── auth.py
├── config.py
├── requirements.txt
├── README.md
├── ai/
├── apps/
├── database/
│   ├── connection.py
│   ├── migrations.py
│   ├── models/
│   └── scripts/
├── docs/
├── scripts/
├── static/
├── templates/
└── tests/
```

## Testes

```powershell
python -m pytest
```

## Release

Para gerar um pacote limpo:

```powershell
python scripts\make_release.py
```

O release exclui itens sensíveis e pesados, como banco SQLite, logs, uploads, `.env`, cache, backups e ambientes virtuais.

## O Que Não Subir Para o GitHub

Não envie dados reais ou arquivos de ambiente para repositórios públicos.

Itens que devem ficar fora do Git:

```text
.env
database/*.db
database/*.db-*
database/*.bak
logs/
static/uploads/
apps/fiscal/instance/uploads/
apps/fiscal/instance/results/
venv/
.venv/
__pycache__/
*.pyc
*.xlsx
*.xls
*.pdf
```

## Problemas Comuns

### `No such file or directory: requirements.txt`

Você provavelmente está dentro de `scripts/` ou outra subpasta. Volte para a raiz do projeto:

```powershell
cd ..
pip install -r requirements.txt
```

### `sqlite3.OperationalError: no such table: usuarios`

Ative a migração automática no `.env`:

```env
AUTO_MIGRATE_ON_STARTUP=1
```

Depois rode pela raiz:

```powershell
python app.py
```

### Erro ao instalar `pandas`

Atualize o pip e use este `requirements.txt`, que deixa o pip escolher versões compatíveis com seu Python:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Segurança

- Defina `SECRET_KEY` forte antes de publicar.
- Use HTTPS em produção.
- Faça backup do banco antes de atualizações.
- Mantenha `AUTO_MIGRATE_ON_STARTUP=0` em produção se preferir aplicar migrações manualmente.
- Revise permissões de usuários e setores periodicamente.
- Não publique bancos, logs, uploads ou credenciais.

## Licença

Defina uma licença antes de publicar este projeto como repositório público.
