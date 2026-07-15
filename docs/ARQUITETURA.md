# Arquitetura

## Visão técnica

O Portal Corporativo é uma aplicação Flask renderizada no servidor. As páginas usam Jinja2, CSS próprio e JavaScript no template base. SQLite armazena os dados principais. Módulos independentes são carregados como blueprints a partir de `apps/`.

## Componentes

| Componente | Responsabilidade |
|---|---|
| `app.py` | Inicialização, rotas centrais, orquestração, contexto global e carregamento de blueprints |
| `config.py` | Configuração derivada do ambiente |
| `auth.py` | Usuário atual e autorização por papel |
| `security.py` | CSRF, cookies de sessão e headers defensivos |
| `database/connection.py` | Caminho dinâmico do banco e conexões seguras |
| `database/migrations.py` | Migrações versionadas e aditivas |
| `database/models/` | Persistência e regras específicas por domínio |
| `templates/` | Páginas Jinja2 e JavaScript global |
| `static/` | CSS, imagens, service worker e arquivos enviados em runtime |
| `ai/` | Prompt corporativo e cliente do Ollama |
| `apps/` | Blueprints opcionais de aplicativos internos |
| `scripts/` | Migração segura, release e recuperação de senha administrativa |
| `tests/` | Testes isolados com cópia temporária do banco |

## Ciclo de inicialização

1. `load_dotenv()` lê o `.env` antes da criação da configuração.
2. `AppConfig` valida ambiente, chave secreta, cookies e flags de startup.
3. A aplicação Flask é criada e recebe proteção CSRF e headers.
4. `inicializar_runtime()` executa migrações apenas se `AUTO_MIGRATE_ON_STARTUP=1`.
5. Se permitido, o bootstrap cria um superadmin somente quando não existe nenhum usuário.
6. Blueprints encontrados em `apps/*` são importados e registrados.
7. Quando executado diretamente, o servidor escuta `0.0.0.0:5007` com debug desativado por padrão.

## Pipeline de requisição

1. A proteção CSRF examina métodos mutáveis.
2. O acesso é registrado na tabela `acessos`.
3. O middleware global exige sessão, exceto login, arquivos estáticos, service worker e honeypot.
4. A configuração de abas pode bloquear áreas para usuários comuns.
5. Decoradores específicos validam papel mínimo.
6. A rota chama modelos de domínio e renderiza HTML ou JSON.
7. Headers de segurança são adicionados à resposta.

## Autorização

`auth.py` define uma ordem de papéis:

```text
comum < recepcao < admin < superadmin
```

Além dos decoradores, algumas regras dependem do setor:

- Gestão de comunicados: admin, superadmin ou setor contendo “gerencia”.
- Indicadores gerenciais: admin, superadmin ou setor reconhecido como gerência.
- Hub de Apps: usuários não administrativos são filtrados por `setores_liberados`.
- Abas desabilitadas: afetam usuários comuns; papéis superiores mantêm acesso.

## Blueprints carregados

| Blueprint | Prefixo | Função atual |
|---|---|---|
| `autonomo_rpa` | `/apps/autonomo_rpa` | Converte planilha de contratos em TXT de importação |
| `fiscal` | `/apps/fiscal` | Dashboard fiscal |
| `gerador_rpa` | `/apps/gerador_rpa` | Gera esqueleto de automação a partir de passos |
| `rh` | `/apps/rh` | Página de treinamentos |
| `reservas` | `/apps/reservas` | Blueprint reservado; as reservas principais estão em `app.py` |

Falhas ao importar um blueprint são registradas no log e não impedem o carregamento dos demais.

## Persistência

Os modelos antigos ainda usam conexões SQLite próprias em alguns domínios; os componentes novos preferem `connect_db()`, que ativa timeout, `foreign_keys` e modo somente leitura quando aplicável. `DATABASE_PATH` é resolvido dinamicamente para permitir testes isolados.

Chamados são criados junto com o vínculo de local na mesma transação. A auditoria também aceita conexão externa quando precisa participar de uma transação administrativa.

## Sincronização no navegador

O template `base.html` consulta `/api/portal/tempo-real` a cada 12 segundos. O servidor devolve versão da área, notificações, pop-up pendente e abas visíveis. Quando a versão muda, a tela recarrega automaticamente, exceto enquanto o usuário está editando um formulário.

Em falhas consecutivas, o intervalo cresce gradualmente até 30 segundos. Chat e IA têm comportamento específico para evitar recarga indevida.

## Pontos de evolução

- Separar rotas centrais por domínio em blueprints.
- Criar camada de serviços para transações que envolvem mais de um modelo.
- Padronizar todos os modelos em `connect_db()`.
- Adicionar servidor WSGI suportado e testes de proxy/HTTPS.
- Avaliar PostgreSQL conforme concorrência e volume.
- Evoluir polling para Server-Sent Events ou WebSocket se houver necessidade real.
