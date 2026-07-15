# Documentação do Portal Corporativo

Este diretório é a referência funcional, técnica e operacional do Portal Corporativo. O código é a fonte final de verdade; quando um comportamento mudar, o documento correspondente deve ser atualizado no mesmo pacote.

## Comece por aqui

| Público | Documento | Objetivo |
|---|---|---|
| Todos | [Visão geral](VISAO_GERAL.md) | Entender finalidade, módulos e limites do portal |
| Usuários e gestores | [Funcionalidades e permissões](FUNCIONALIDADES_E_PERMISSOES.md) | Saber o que cada perfil pode fazer |
| TI/implantação | [Instalação e configuração](INSTALACAO_E_CONFIGURACAO.md) | Preparar Windows ou Linux e configurar o `.env` |
| Desenvolvimento | [Arquitetura](ARQUITETURA.md) | Entender componentes, fluxo de requisição e organização do código |
| Desenvolvimento | [Guia de desenvolvimento](DESENVOLVIMENTO.md) | Alterar módulos sem comprometer dados e segurança |
| Banco/DBA | [Banco, migrações e preservação](BANCO_MIGRACOES_E_PRESERVACAO.md) | Conhecer tabelas, migrações e regras de preservação |
| Operação | [Operação, deploy e rollback](OPERACAO_DEPLOY_E_ROLLBACK.md) | Atualizar, iniciar, parar e voltar uma versão |
| Segurança | [Segurança e auditoria](SEGURANCA_E_AUDITORIA.md) | Compreender CSRF, sessões, logs, honeypot e trilha imutável |
| QA | [Testes e qualidade](TESTES_E_QUALIDADE.md) | Executar e ampliar a suíte automatizada |
| Suporte | [Solução de problemas](SOLUCAO_DE_PROBLEMAS.md) | Diagnosticar login, CSRF, porta, banco e erros 500 |
| Integrações | [Tempo real e notificações](TEMPO_REAL_E_NOTIFICACOES.md) | Entender sincronização, pop-ups e notificações desktop |
| Referência | [Rotas e APIs](ROTAS_E_APIS.md) | Consultar endpoints, métodos e autorização |
| Referência | [Dicionário de dados](DICIONARIO_DE_DADOS.md) | Consultar finalidade e relações das tabelas |

## Estado técnico documentado

- Aplicação Flask com templates Jinja2 e SQLite.
- Porta direta do `app.py`: `5007`.
- Migrações automáticas desativadas por padrão.
- Migrações explícitas com backup e prova de preservação.
- Perfis `comum`, `recepcao`, `admin` e `superadmin`.
- Locais de trabalho: Sede, Filial e Remoto.
- Atualização do portal por consulta periódica a cada 12 segundos, com recuo até 30 segundos em caso de falha.
- Notificações internas, pop-ups agendados e notificações desktop quando o navegador permite.
- Auditoria append-only com cadeia de hashes.
- Exclusão lógica nos módulos críticos.
- Pacotes de release sem banco, `.env`, logs, uploads ou documentos internos.

## Comandos essenciais

```bash
python scripts/migrate_database.py
python -m pytest -q
python app.py
python scripts/make_release.py
```

Nunca execute migrações ou testes diretamente contra o banco de produção sem seguir os procedimentos documentados.
