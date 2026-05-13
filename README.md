# n8n Backup/Restore via MCP

Aplicação desktop em Python para:
- Cadastrar servidores n8n via MCP
- Fazer backup de workflows MCP-liberados
- Restaurar workflows a partir de diretórios de backup

## Requisitos

- Python 3.11+
- Endpoint MCP HTTP do n8n com autenticação `Authorization: Bearer <token>`

## Instalação

```bash
pip install -e .[dev]
```

## Execução

```bash
n8n-backup-restore
```

ou:

```bash
python -m n8n_backup_restore.main
```

## Estrutura de dados

- Configuração: `./config/settings.json`
- Backups: `./backups/{YYYYMMDD_HHmmSS}_{serverAlias}`
- Logs: `./logs/app_{YYYYMMDD}.log`

Cada workflow exportado gera:
- `{workflowName_workflowId}.json` (nome sanitizado)

## Testes

```bash
pytest -q
```

## Executável

### Windows
```bash
pyinstaller --name n8n-backup-restore --windowed --onefile --paths src src/n8n_backup_restore/main.py
```

### Linux/macOS
```bash
pyinstaller --name n8n-backup-restore --windowed --onefile --paths src src/n8n_backup_restore/main.py
```

Saída em `dist/`.
