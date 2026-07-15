# Auditoria, preservação e unidades

## Princípios adotados

- Dados existentes não são reclassificados automaticamente.
- Ausência de vínculo com unidade significa `não definido` ou `compartilhado`, conforme o módulo.
- Exclusões administrativas dos módulos críticos são lógicas: o registro e seu ID permanecem no banco.
- Arquivos de POP removidos do mural permanecem no armazenamento.
- Antes de substituir os indicadores atuais, uma importação arquiva integralmente a base anterior.

## Auditoria

A tabela `auditoria_eventos` registra novas alterações relevantes com usuário, ID, data/hora, ação, módulo, registro, valores anterior/novo em JSON, unidade, IP, navegador e hash encadeado de integridade.

Triggers do SQLite impedem `UPDATE` e `DELETE` nessa tabela. A tela `/admin/auditoria` é restrita a administradores e superadministradores.

## Sede, Filial e Remoto

Os locais `SEDE`, `FILIAL` e `REMOTO` são cadastrados por migrações aditivas. Nenhum usuário, sala, atendimento ou outro registro antigo é associado automaticamente. Superadministradores podem fazer associações graduais pelas telas de usuários, salas e locais de trabalho.

Novos chamados herdam o local do usuário que os abriu. Usuários ainda não classificados geram chamados com escopo `nao_definido`, sem erro e sem classificação automática. A criação do chamado e de seu vínculo ocorre na mesma transação, evitando registros parcialmente salvos.

## Aplicação segura da migração

Execute na raiz do projeto:

```powershell
python scripts\migrate_database.py
```

O script cria um backup SQLite consistente, executa apenas migrações aditivas e compara hashes lógicos de todas as tabelas anteriores.

Depois de migrar um ambiente controlado, recomenda-se configurar `AUTO_MIGRATE_ON_STARTUP=0` e aplicar futuras migrações explicitamente antes de reiniciar o serviço.
