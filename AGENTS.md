# AGENTS.md

Este arquivo e o ponto de entrada para qualquer agente de IA neste repositorio.
Antes de propor mudancas, leia este arquivo inteiro.

## 1) Contexto do produto

- Projeto: `n8n-backup-restore`
- Tipo: aplicacao desktop em Python (PySide6)
- Objetivo: fazer backup e restore de workflows do n8n por ambiente.
- Usuario alvo: operador/engenharia que administra instancias n8n.

## 2) Regra de negocio (essencial)

- O usuario cadastra servidores n8n com:
  - alias
  - URL base da instancia
  - API key
- Backup:
  - lista workflows no servidor escolhido
  - usuario seleciona workflows
  - app salva cada workflow em JSON em pasta timestamp
- Restore:
  - usuario escolhe servidor destino e pasta de backup
  - app restaura workflows selecionados
  - se houver conflito por nome:
    1. renomeia o workflow atual com sufixo de inativacao
    2. arquiva/desativa workflow atual
    3. cria novo workflow a partir do backup
- Delete definitivo e propositalmente bloqueado por seguranca.

## 3) Arquitetura (mapa rapido)

- Entrada da app: `src/n8n_backup_restore/main.py`
- UI principal: `src/n8n_backup_restore/ui/main_window.py`
- Modelos: `src/n8n_backup_restore/models/entities.py`
- Persistencia de configuracao: `src/n8n_backup_restore/storage/settings_store.py`
- Servicos:
  - `src/n8n_backup_restore/services/workflow_mcp_service.py`
  - `src/n8n_backup_restore/services/backup_service.py`
  - `src/n8n_backup_restore/services/restore_service.py`
  - `src/n8n_backup_restore/services/mcp_client.py` (legado/compatibilidade)
- Utilitarios:
  - `src/n8n_backup_restore/utils/files.py`
  - `src/n8n_backup_restore/utils/logging_setup.py`

## 4) Integracao com n8n (estado atual)

- Autenticacao: header `X-N8N-API-KEY`.
- Endpoints usados:
  - `GET /api/v1/workflows`
  - `GET /api/v1/workflows/{id}`
  - `POST /api/v1/workflows`
  - `PATCH /api/v1/workflows/{id}` (com fallback para `PUT`)
  - `POST /api/v1/workflows/{id}/archive` (fallback para `deactivate`)
  - `POST /api/v1/workflows/{id}/activate`

## 5) Persistencia local

- Configuracao: `config/settings.json`
- Backups: `backups/{YYYYMMDD_HHmmSS}_{serverAlias}`
- Logs: `logs/app_{YYYYMMDD}.log`

## 6) Versionamento e release

- Versao atual deve estar sincronizada entre:
  - `pyproject.toml`
  - `src/n8n_backup_restore/__init__.py`
  - `CHANGELOG.md`
- Padrao de versao: Semantic Versioning.

## 7) Como rodar

- Instalar:
  - `pip install -e .[dev]`
- Executar:
  - `n8n-backup-restore`
  - ou `python -m n8n_backup_restore.main`
- Testes:
  - `python -m pytest -q`

## 8) Regras para agentes

- Nao fazer refactor amplo sem pedido explicito.
- Preservar fluxo de backup/restore e regra de conflito.
- Manter mudancas pequenas e testaveis.
- Ao mudar comportamento de negocio, atualizar:
  - `CHANGELOG.md`
  - `docs/agents/SESSION_MEMORY.md`
  - `docs/agents/DECISIONS.md` (se houver decisao tecnica)

## 9) Memoria de projeto para novos chats

Ler nesta ordem:

1. `AGENTS.md` (este arquivo)
2. `docs/agents/SESSION_MEMORY.md`
3. `docs/agents/BACKLOG.md`
4. `docs/agents/DECISIONS.md`
5. `README.md`
6. `CHANGELOG.md`

## 10) Estado atual resumido

- Versao: `0.1.0`
- App desktop funcional para backup/restore.
- Testes automatizados presentes e passando.
- Estrutura de contexto para agentes centralizada em `AGENTS.md` + `docs/agents/*`.

