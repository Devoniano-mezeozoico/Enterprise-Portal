# Arquitetura e segurança do Portal Corporativo

Este documento registra as decisões de endurecimento aplicadas ao projeto e o caminho recomendado para evoluir o portal com segurança.

## O que já foi endurecido

- Configuração centralizada em `config.py`.
- Remoção da chave secreta fixa como fallback.
- Em produção, `SECRET_KEY` passa a ser obrigatória.
- Em desenvolvimento sem `SECRET_KEY`, o app usa chave temporária e emite alerta.
- Proteção CSRF em formulários mutáveis.
- Headers básicos de segurança em todas as respostas.
- Inicialização de banco/bootstrap movida para `inicializar_runtime()` com flags de ambiente.
- Script de release seguro em `scripts/make_release.py`, excluindo `.env`, bancos, logs, uploads, PDFs, planilhas, caches e zips antigos.
- Suíte `pytest` com banco copiado para diretório temporário.
- Auditoria imutável e encadeada por hash para alterações relevantes.
- Modelo incremental de sede/filial sem classificação automática de dados antigos.
- Remoção lógica nos módulos críticos e preservação dos arquivos de POP.
- Histórico das bases de atendimento antes de cada nova importação.
- Caminho do banco alinhado à variável `DATABASE_PATH` também nos modelos.
- Carregamento efetivo do `.env` antes da configuração e debug desativado por padrão.

## Variáveis importantes

- `APP_ENV=production`
- `SECRET_KEY=<chave-forte>`
- `DATABASE_PATH=database/intranet.db`
- `LOG_DIR=logs`
- `AUTO_MIGRATE_ON_STARTUP=1`
- `BOOTSTRAP_SUPERADMIN_ON_STARTUP=1`
- `LOAD_BLUEPRINTS_ON_STARTUP=1`
- `SESSION_COOKIE_SECURE=1`
- `CSRF_ENABLED=1`

Use `.env.example` como base. O `.env` real não deve ser enviado.

## Como testar

```bash
python -m pytest -q
```

Os testes copiam o banco para um diretório temporário. Não devem rodar contra o banco real.

## Como gerar pacote seguro

```bash
python scripts/make_release.py
```

O pacote será gerado em `release/` sem dados sensíveis.

## Próximos passos recomendados

1. Dividir `app.py` em blueprints por domínio:
   - `routes/auth.py`
   - `routes/comunicados.py`
   - `routes/noticias.py`
   - `routes/pops.py`
   - `routes/agenda.py`
   - `routes/admin.py`

2. Criar camada de serviços:
   - `services/notificacoes_service.py`
   - `services/comunicados_service.py`
   - `services/search_service.py`
   - `services/realtime_service.py`

3. Separar migrações do startup:
   - manter `AUTO_MIGRATE_ON_STARTUP=1` apenas em ambientes controlados;
   - criar comando administrativo para aplicar migrações antes do deploy.

4. Avaliar banco:
   - SQLite continua aceitável para intranet pequena/média;
   - se crescer acesso simultâneo, migrar para PostgreSQL.

5. Aumentar cobertura de testes:
   - autenticação;
   - permissões por papel/setor;
   - upload/download;
   - notificações desktop;
   - bloqueio de abas para usuários comuns.
