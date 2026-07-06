[README.md](https://github.com/user-attachments/files/29717625/README.md)
# Enterprise portal - Intranet Corporativa

Enterprise portal é uma intranet corporativa desenvolvida em Flask para centralizar notícias internas, POPs, Hub de Apps, agenda, reservas, chamados, indicadores, chat e ferramentas administrativas em um único ambiente.

O projeto foi pensado para uso interno, com controle de permissões por perfil e por setor, preservação de registros e recursos de administração para manter a operação do portal simples no dia a dia.

> Importante: antes de publicar este projeto no GitHub, remova dados sensíveis. Não versionar banco real, arquivos enviados, logs, `.env` ou qualquer credencial.

## Funcionalidades

### Início

- Notícias em destaque no topo.
- POPs recentes em formato de leitura rápida.
- Reservas do dia.
- Painel "Próximos Eventos Enterprise portal".
- Indicadores de atendimentos filtrados pelo setor do usuário logado.
- Acesso rápido aos apps liberados para o usuário.

### Autenticação e Perfis

O sistema possui autenticação por e-mail e senha, com senhas armazenadas por hash.

Perfis disponíveis:

- `comum`: acessa a intranet e recursos liberados para seu setor.
- `recepcao`: pode cadastrar eventos e reservas.
- `admin`: acessa áreas administrativas básicas.
- `superadmin`: gerencia usuários, permissões e configurações sensíveis.

### Hub de Apps

- Cadastro de sistemas internos e externos.
- Apps agrupados por setor.
- Permissão por setor via campo `setores_liberados`.
- Admins e superadmins visualizam todos os apps.
- Usuários comuns visualizam apenas apps liberados para seu setor.
- Suporte ao app ADF por `/apps/adf` ou variável `ADF_URL`.

Exemplos de permissão:

```text
TI
Fiscal,RH
Todos
```

### Notícias

- Cadastro de notícias internas.
- Suporte a anexos.
- Imagens podem ser exibidas junto da notícia.
- PDFs e demais arquivos podem ser baixados.

### POPs

- Upload e organização de POPs.
- Categorias por área.
- Visualização no próprio portal quando possível.
- Download de arquivos.
- Busca por conteúdo relevante para uso pela IA.

### Agenda e Reservas

- Calendário mensal.
- Cadastro de reservas de salas.
- Cadastro de eventos internos Enterprise portal.
- Diferenciação visual entre reserva e evento interno.
- Eventos internos aparecem na home em "Próximos Eventos Enterprise portal".

### Chat Interno

- Chat entre usuários autenticados.
- Mensagens apagadas deixam de aparecer para usuários comuns.
- Admins e superadmins podem visualizar mensagens apagadas.
- Logs separados para auditoria de mensagens enviadas e apagadas.

### Chamados e Estoque de TI

- Abertura e acompanhamento de chamados de TI.
- Controle básico de estoque.
- Gestão por administradores.

### Indicadores de Atendimento

- Upload de planilhas `.xlsx` ou `.xls`.
- Processamento de planilhas brutas ou já consolidadas.
- Cálculo de quantidade de atendimentos.
- Cálculo de tempo médio de resposta.
- Exibição filtrada pelo setor do usuário logado.

### IA Corporativa

- Integração com Ollama.
- Consulta a POPs, notícias e eventos da agenda.
- Endpoint `/api/ia`.
- Configuração por variáveis de ambiente.

### Honeypot Administrativo

- Rotas isca como `/admin`, `/painel`, `/wp-admin`, `/phpmyadmin` e `/admin_painel`.
- Delay em tentativas de POST.
- Registro de IP, rota, referer e user agent.
- Classificação básica de risco.
- Painel administrativo real para análise das tentativas.

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
- Ollama
- Font Awesome

## Estrutura do Projeto

```text
Enterprise_portal/
├── app.py
├── auth.py
├── requirements.txt
├── README.md
├── ai/
│   ├── ollama.py
│   ├── prompts.py
│   └── teste_ai.py
├── apps/
│   ├── autonomo_rpa/
│   ├── fiscal/
│   ├── gerador_rpa/
│   ├── reservas/
│   └── rh/
├── database/
│   ├── intranet.db              # não versionar em produção
│   ├── honeypot.db              # não versionar em produção
│   ├── models/
│   └── scripts/
├── logs/                        # não versionar
├── static/
│   ├── img/
│   ├── uploads/                 # não versionar arquivos reais
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html
    ├── login.html
    ├── hub_apps.html
    ├── agenda.html
    ├── chat.html
    ├── admin_apps.html
    ├── admin_usuarios.html
    ├── admin_honeypot.html
    └── honeypot/
```

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/enterprise-portal.git
cd enterprise-portal
```

### 2. Criar ambiente virtual

Windows:

```powershell
python -m venv venv
.\venv\Scripts\activate
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
SECRET_KEY=troque-esta-chave
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
ADF_URL=
```

Variáveis:

- `SECRET_KEY`: chave usada pelo Flask para sessões.
- `OLLAMA_URL`: endereço do servidor Ollama.
- `OLLAMA_MODEL`: modelo utilizado pela IA.
- `ADF_URL`: URL real do sistema ADF. Se vazia, o portal usa `/apps/adf` como fallback.

### 5. Iniciar o portal

```bash
python app.py
```

Acesse:

```text
http://127.0.0.1:5000/login
```

## Banco de Dados

O projeto usa SQLite.

Na inicialização, `app.py` executa migrações aditivas com `CREATE TABLE IF NOT EXISTS` e `ALTER TABLE` quando necessário. Isso evita apagar dados já existentes.

Tabelas principais:

- `usuarios`
- `noticias`
- `pops`
- `hub_apps`
- `eventos_agenda`
- `reservas`
- `chat_mensagens`
- `chamados_ti`
- `estoque_ti`
- `atendimento_metricas`
- `honeypot_tentativas`

Nunca suba o banco real para repositórios públicos.

Arquivos que devem ficar fora do Git:

```text
database/intranet.db
database/honeypot.db
database/*.bak
logs/
static/uploads/*
.env
__pycache__/
*.pyc
```

## Primeiro Acesso

Se o banco estiver vazio, o sistema cria automaticamente um superadmin temporário.

A senha temporária é registrada em:

```bash
logs/app.log
```

Para localizar:

```bash
cat logs/app.log | grep "Senha temporária"
```

No Windows PowerShell:

```powershell
Get-Content logs\app.log | Select-String "Senha temporária"
```

Após entrar, troque ou recrie as credenciais conforme a política interna.

## Permissões por Setor no Hub Apps

Cada app possui:

- `setor`: setor/categoria principal do app.
- `setores_liberados`: setores que podem visualizar o app.

Regras:

- `superadmin` e `admin` visualizam todos os apps.
- Usuário comum visualiza apenas apps liberados para o setor cadastrado no usuário.
- `Todos`, `Geral` ou `Global` liberam acesso amplo.

Exemplo:

```text
Nome: ADF
Setor: Geral
Setores liberados: Todos
Icone: fa-solid fa-diagram-project
URL: /apps/adf
```

## Ícones Úteis

O portal usa Font Awesome.

Sugestões usadas no projeto:

```text
ADF:                  fa-solid fa-diagram-project
Eventos internos:     fa-solid fa-calendar-check
Salvar:               fa-solid fa-floppy-disk
Hub de Apps:          fa-solid fa-mobile-screen
Gerenciar Apps:       fa-solid fa-grid-2
Atendimentos:         fa-solid fa-chart-simple
Gráfico:              fa-solid fa-chart-bar
Tempo médio:          fa-solid fa-clock
Usuários:             fa-solid fa-users-gear
Honeypot:             fa-solid fa-fingerprint
Estoque:              fa-solid fa-boxes-stacked
Chat:                 fa-solid fa-comments
POPs:                 fa-solid fa-book
Notícias:             fa-solid fa-newspaper
Agenda:               fa-solid fa-calendar-days
```

## Upload de Indicadores

Admins e superadmins podem enviar planilhas de atendimento.

O sistema aceita:

- planilha bruta, agrupando por responsável/departamento;
- planilha já consolidada, com quantidade e tempo médio.

Os indicadores da tela inicial são filtrados pelo setor do usuário logado para evitar exibição indevida de dados de outros setores.

## IA com Ollama

Para usar a IA:

```bash
ollama serve
ollama pull llama3
python app.py
```

Teste manual:

```bash
python -m ai.teste_ai "Quais POPs existem sobre fiscal?"
```

## Segurança e Operação

Recomendações:

- Não versionar `.env`.
- Não versionar bancos SQLite reais.
- Não versionar logs.
- Não versionar uploads internos.
- Usar `SECRET_KEY` forte em produção.
- Fazer backup do banco antes de qualquer atualização.
- Rodar atrás de servidor WSGI/reverso em produção.
- Revisar permissões dos usuários e setores periodicamente.

## Rotas Principais

```text
/login
/
/noticias
/pops
/apps
/agenda
/chat
/ti/chamados
/ti/estoque
/admin/apps
/admin/usuarios
/admin/atendimentos
/admin/acessos
/admin/honeypot
/ia
```

Rotas isca do honeypot:

```text
/admin
/painel
/wp-admin
/phpmyadmin
/admin_painel
```

## Deploy Seguro

Ao subir uma nova versão:

1. Faça backup de `database/intranet.db`.
2. Faça backup de `static/uploads/`.
3. Suba apenas código, templates e arquivos estáticos versionáveis.
4. Não sobrescreva o banco real com banco vazio.
5. Reinicie o serviço.
6. Acesse `/login`.
7. Teste `/`, `/apps`, `/agenda` e `/admin/apps`.

## Status do Projeto

Projeto em uso interno, com módulos ativos para intranet, gestão administrativa, indicadores, chat, agenda e segurança defensiva.

## Licença

Uso interno do Enterprise portal. Defina uma licença antes de publicar este projeto como repositório público.
