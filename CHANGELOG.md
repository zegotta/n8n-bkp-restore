
# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e este projeto adota [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added
- Nova aba de comparacao de backups com selecao de dois backups e listagem lado a lado dos fluxos.
- Indicacao de status por fluxo: `IGUAL`, `DIFERENTE`, `SO_NO_BACKUP_A` e `SO_NO_BACKUP_B`.

## [0.1.0] - 2026-05-13

### Added
- Aplicação desktop com interface PySide6 para gerenciar servidores n8n.
- Fluxo de backup de workflows com exportação em JSON.
- Fluxo de restore com resolução de conflitos e opções de publicação.
- Configurações persistidas em arquivo local.
- Testes automatizados para serviços principais.
