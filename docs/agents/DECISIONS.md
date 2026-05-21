# DECISIONS.md

Registre aqui decisoes tecnicas que afetam arquitetura, regra de negocio ou operacao.

## Formato

```
## [YYYY-MM-DD] Titulo curto
Contexto:
Decisao:
Impacto:
Alternativas consideradas:
```

## Entradas

## [2026-05-13] Versionamento semantico com changelog
Contexto:
Projeto precisava de historico de versoes e consistencia da versao.
Decisao:
Adotar SemVer e manter `CHANGELOG.md` com secao `Unreleased`.
Impacto:
Maior previsibilidade de releases e rastreabilidade de mudancas.
Alternativas consideradas:
Manter versao apenas no `pyproject.toml` sem changelog estruturado.

## [2026-05-21] Contexto persistente para agentes em AGENTS.md
Contexto:
Necessidade de evitar reexplicar o projeto em novos chats.
Decisao:
Centralizar contexto em `AGENTS.md` e manter memoria complementar em `docs/agents/*`.
Impacto:
Onboarding de novos agentes fica padronizado e mais rapido.
Alternativas consideradas:
Manter contexto distribuido somente em README e arquivos soltos.

## [2026-05-21] Limpar listas de fluxos ao trocar servidor
Contexto:
Usuario percebeu risco de confusao por manter lista de fluxos carregada de uma selecao antiga de servidor.
Decisao:
Sempre limpar a tabela/lista de fluxos quando o servidor selecionado muda nas telas de Backup e Restore.
Impacto:
Evita operacoes em dados stale e melhora previsibilidade da UI.
Alternativas consideradas:
Manter lista antiga e depender de reload manual.
