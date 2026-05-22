
# Changelog

Todas as mudanças relevantes deste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e este projeto adota [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added
- Nova aba de comparacao de backups com selecao de dois backups e listagem lado a lado dos fluxos.
- Indicacao de status por fluxo: `IGUAL`, `DIFERENTE`, `SO_NO_BACKUP_A` e `SO_NO_BACKUP_B`.

### Fixed
- Comparacao cross-server agora ignora `workflowInputs.matchingColumns`, evitando falso positivo gerado por metadata da UI do n8n em nodes `Execute Workflow`.
- Comparacao de backups agora ignora conexoes orfas que referenciam nodes inexistentes no workflow, reduzindo falso positivo em diffs estruturais sem impacto funcional.
- Comparacao cross-server agora ignora campos removidos e o flag `removed` em `workflowInputs.schema`, evitando falso positivo de metadata da UI do n8n.
- Comparacao cross-server agora ignora ids internos de regras/condicoes do n8n e a ordem da lista `nodes`, evitando falso positivo quando a logica e as conexoes permanecem iguais.

## [0.1.0] - 2026-05-13

### Added
- Aplicação desktop com interface PySide6 para gerenciar servidores n8n.
- Fluxo de backup de workflows com exportação em JSON.
- Fluxo de restore com resolução de conflitos e opções de publicação.
- Configurações persistidas em arquivo local.
- Testes automatizados para serviços principais.
