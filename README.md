# n8n Backup/Restore

Aplicacao desktop (PySide6) para backup e restore de workflows do n8n.

## O que o app faz

- Cadastro de multiplos servidores n8n (alias, URL da instancia e API Key).
- Teste de conexao com a API n8n.
- Listagem de workflows e backup em arquivos `.json`.
- Restore seletivo de workflows a partir de uma pasta de backup.
- Comparacao entre 2 backups com visao lado a lado dos fluxos.
- Tratamento de conflito no restore:
  - renomeia e arquiva workflow existente
  - cria nova versao a partir do backup
- Opcao de publicar workflows criados no restore.

## Requisitos

- Python 3.11+
- n8n com API habilitada
- API Key valida para cada instancia n8n

Autenticacao usada nas chamadas da API:
- Header: `X-N8N-API-KEY: <api_key>`

## Instalacao

```bash
pip install -e .[dev]
```

## Execucao

```bash
n8n-backup-restore
```

ou

```bash
python -m n8n_backup_restore.main
```

## Estrutura de dados local

- Configuracao: `./config/settings.json`
- Backups: `./backups/{YYYYMMDD_HHmmSS}_{serverAlias}`
- Logs: `./logs/app_{YYYYMMDD}.log`

Cada workflow exportado gera:
- `{workflowName}_{workflowId}.json` (nome sanitizado)

## Testes

```bash
python -m pytest -q
```

## Versionamento

- O projeto segue Semantic Versioning.
- Historico de versoes em `CHANGELOG.md`.
- A versao atual deve ficar sincronizada entre:
  - `pyproject.toml` (`project.version`)
  - `src/n8n_backup_restore/__init__.py` (`__version__`)
  - secao da versao atual em `CHANGELOG.md`

## Contexto entre chats

- Arquivo principal para agentes: `AGENTS.md`
- Memoria de sessao: `docs/agents/SESSION_MEMORY.md`
- Prompt base para novo chat: `docs/agents/NEW_CHAT_PROMPT.md`

## Build do executavel

### Windows

```bash
pyinstaller --name n8n-backup-restore --windowed --onefile --paths src src/n8n_backup_restore/main.py
```

### Linux/macOS

```bash
pyinstaller --name n8n-backup-restore --windowed --onefile --paths src src/n8n_backup_restore/main.py
```

Saida em `dist/`.
