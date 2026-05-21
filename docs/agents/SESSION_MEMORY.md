# SESSION_MEMORY.md

## Ultima atualizacao

2026-05-21 (atualizado)

## Estado atual

- Projeto em versao `0.1.0`.
- App desktop para backup/restore de workflows n8n funcional.
- Versionamento semantico configurado com `CHANGELOG.md`.
- Testes automatizados existentes e estaveis.

## Contexto operacional importante

- Autenticacao de API usa `X-N8N-API-KEY`.
- Restore com conflito nao sobrescreve direto:
  - renomeia e arquiva workflow atual
  - cria um novo workflow com dados do backup
- Delete definitivo de workflow esta desabilitado por seguranca.

## Ultimas mudancas relevantes

- Documentacao base para agentes centralizada em `AGENTS.md`.
- Estrutura auxiliar para memoria de sessao criada em `docs/agents/*`.
- Tela de comparacao de backups evoluida com:
  - comparacao por nome
  - filtros opcionais para `settings` e URLs/endpoints
  - botao de detalhe por linha com diff em janela modal
  - realce visual de diferencas de string sem truncamento
- Ao trocar servidor na tela de Backup e Restore, a lista de fluxos eh limpa para evitar dados da selecao anterior.

## Proximos passos sugeridos

- Revisar backlog e priorizar entregas da proxima sprint.
- Adicionar testes de integracao para erros comuns da API n8n.
