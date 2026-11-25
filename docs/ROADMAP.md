# EngiFlow — Roadmap

Legenda de status: **Implementado · Testado · Simulado · Pendente de homologação · Bloqueado por dependência externa · Planejado**.

Hoje todas as fases estão em **Planejado**.

| Fase | Entrega | Critério de saída | Status |
|---|---|---|---|
| 0 | Discovery e arquitetura (esta fase) | documentos, ADRs, backlog e critérios de aceite apresentados para revisão | Planejado (documentação entregue como proposta) |
| 1 | Foundation: monorepo, Docker Compose, frontend, backend, PostgreSQL, migrações, autenticação, organizações, permissões, dashboard inicial, auditoria básica, CI/CD | CI verde; login, isolamento e auditoria testados | Planejado — **aguarda aprovação da Fase 0** |
| 2 | Data Studio: importação Excel/CSV, mapeamento, normalização, comparação, duplicatas, transformações, exportação, templates | fixtures de planilhas inconsistentes passando | Planejado |
| 3 | Engineering Core: projetos, materiais, BOM multinível, expansão, quantidades, classificação, revisões, comparação, exportação ERP | CA-01 a CA-12 do PRD | Planejado |
| 4 | Local Agent e CAD: registro, comunicação segura, executor, mock, conector Solid Edge somente leitura, extração e validação | agente testado em estação real | Planejado; **Solid Edge bloqueado por dependência externa** (ambiente e licença) |
| 5 | ERP e Inventory: importação Protheus, estoque, conferência, CAD vs ERP, divergências | arquivos Protheus reais validados | Planejado; **Protheus API bloqueado** |
| 6 | Workflow Studio: catálogo, executor, editor visual, agendamento, condições, histórico, aprovações, templates | run linear e condicional com retentativa e recuperação testadas | Planejado |
| 7 | Document Center e AI Copilot: documentos, extração, busca textual e semântica, RAG, tool calling, execução controlada | avaliação do copiloto com perguntas sintéticas | Planejado; depende de decisão de provedor de IA |
| 8 | Enterprise: segurança avançada, auditoria completa, indicadores, otimização, homologação, implantação, documentação operacional | teste de restauração e pentest | Planejado |
| 9 | Expansão contínua (Production Planning, Quality, Cost, Supplier, Maintenance, Logistics, processos, ordens, rastreabilidade) | avaliação por necessidade real | Planejado — **não iniciar antecipadamente** |

## Marcos (milestones) sugeridos

- **M1 — MVP interno (fim da Fase 3):** fluxo de 17 passos com dados sintéticos e importação real operada manualmente.
- **M2 — Piloto de agente (fim da Fase 4):** uma estação, Solid Edge somente leitura.
- **M3 — Integração ERP (fim da Fase 5):** arquivos Protheus em homologação.

Datas: **não definidas**. Dependem de decisões em `decisions/OPEN_QUESTIONS.md`. Não há estimativa de prazo confiável sem definição de equipe e disponibilidade.

## Complexidade relativa (não é prazo)

| Fase | Complexidade | Principal incerteza |
|---|---|---|
| 1 | Média | escolha de SSO e infraestrutura |
| 2 | Média | variedade de planilhas reais |
| 3 | Alta | regras de kit e reserva |
| 4 | Alta | COM e licenciamento |
| 5 | Alta | disponibilidade de integração ERP |
| 6 | Alta | estabilidade do executor |
| 7 | Média-alta | qualidade e custo de IA |

## Status atualizado (2026-11-24)

| Fase | Estado | Evidência |
|---|---|---|
| 0 — Discovery e arquitetura | Concluída (documentação, ADRs 0001–0012 revisadas) | `docs/decisions/REVISAO_FASE_0.md` |
| 1 — Foundation | Concluída, com PostgreSQL 17 validado pelo CI | `docs/operations/FASE_1_STATUS.md` |
| 2A — Data Studio | **Concluída** (merge do PR #1 por squash, CI da `main` verde) | `docs/operations/FASE_2_STATUS.md` |
| 2B.1 — Fundação das transformações | Em homologação no PR #2 (CI verde em PostgreSQL 17, 116 testes); integridade revisada (9 testes novos) | `docs/operations/FASE_2B1_STATUS.md` |
| 2B.2 — Manipulação de dados e interface funcional | **Concluída** (PR #3 mesclado em main, commit 90cb12e); limitações de desempenho registradas para a 2B.4 | docs/operations/FASE_2B2_STATUS.md |
| 2B.3 — Cruzamento e comparação de tabelas | **Em implementação** no branch `feat/fase-2b-3-data-crossing` (Super-PROCV, junções, comparação, agrupamento) | `docs/roadmap/FASE_2B3_PLANO.md` |
| 2B.4 — Refinamentos (virtualização, cálculos, medições) | Planejada em `docs/roadmap/FASE_2B_PLANO.md` | — |
| 3 — BOM Manager | Não iniciada (não autorizada) | — |



## Roadmap oficial (atualizado em 2026-11-25)

- Fase 0 — Arquitetura e planejamento
- Fase 1 — Fundação
- Fase 2A — Data Studio Core
- **Fase 2B — Data Studio completo** (em revisão final; ver docs/roadmap/FASE_2B_CONSOLIDACAO.md e docs/operations/FASE_2B3_STATUS.md)
- Fase 3 — Estabilização, correções e otimização do Data Studio
- Fase 4 — BOM Manager
- Fase 5 — Material Manager
- Fase 6 — Inventory Manager
- Fase 7 — Solid Edge Connect
- Fase 8 — ERP Connect
- Fase 9 — Workflow Studio
- Fase 10 — AI Copilot

Os documentos das subdivisões anteriores (2B.1, 2B.2, 2B.3 bloco 1) são históricos e foram preservados.
