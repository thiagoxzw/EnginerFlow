# Checkpoint da Fase 2B.3 (retomada após reset de contexto)

Atualizado em 2026-11-25. Leia este arquivo antes de continuar. Ele não substitui o histórico do Git.

## Onde estamos

- Branch: `feat/fase-2b-3-data-crossing`. PR #4 em draft. **Não fazer merge** sem autorização.
- Fase 2B.4 não iniciada. Não iniciar sem autorização.
- Commits relevantes: `70f582d` (benchmark com recusa), depois as alterações de idempotência, linhagem,
  modos de comparação, isolamento E2E e benchmark dedicado (ver `git log`).

## Ambientes (ver também `docs/operations/LOCAL_SETUP.md`)

| Ambiente | Projeto Compose | Portas | Volumes | Finalidade |
|---|---|---|---|---|
| Demonstrativo pessoal | `engiflow` | web 3000, api 8000, pg 5432 | `engiflow_engiflow-pgdata`, `engiflow_engiflow-data` | uso pessoal. **Não tocar sem autorização** |
| Auditoria (2026-11) | `engiflow-audit` | web 3100, api 8100, pg 5433 | `engiflow-audit_*` | evidências da auditoria visual. Parado após a homologação; volumes preservados |
| E2E descartável | `engiflow-e2e` | web 3210, api 8210, pg 5542 | removidos ao final | `scripts\e2e\Run-E2E.ps1` |
| Benchmark dedicado | `engiflow-bench` | pg 5552 | `engiflow-bench_engiflow-bench-pgdata` | `scripts\bench\Run-Bench.ps1` |

Banco `engiflow_bench` que foi criado dentro do Postgres **demonstrativo** em sessão anterior: existe ainda.
Não foi excluído. Só deve ser removido com autorização explícita, depois de confirmar que nenhum processo depende dele.

## Comandos de verificação

- Backend: `apps\api\.venv\Scripts\python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy src tests`, `-m pytest -q`
- Web: `pnpm typecheck`, `pnpm lint`, `pnpm test -- --run` (em `apps\web`)
- E2E isolado: `scripts\e2e\Run-E2E.ps1`
- Benchmark isolado: `scripts\bench\Run-Bench.ps1 -Rows 500000`

## Pendências (ordem)

1. E2E isolado: último resultado no log da sessão; repetir após correções.
2. Benchmark 500 mil no ambiente dedicado, registrando cada caso ao concluir.
3. Investigação de testes web intermitentes (hipótese: fila de `mockResolvedValueOnce` com `vi.clearAllMocks`).
4. Validação das falhas parciais de importação.
5. Reorganização visual do Data Studio com capturas antes/depois.
6. Suíte final, relatórios, CI do GitHub no commit final, atualização do demo.

## Limitações conhecidas

Ver `docs/operations/FASE_2B3_STATUS.md` (a ser concluído na etapa 8).

## Progresso (2026-11-25, tarde)
- E2E isolado (portas 3210/8210/5542): 15/15 aprovados; stack removido ao final sem deixar volumes.
- Benchmark: runner dedicado (engiflow-bench, porta 5552). Execuções 500k dos dois cenários em andamento; logs em %TEMP%\bench-w500.txt e bench-d500.txt.
- Pendências: testes web intermitentes (hipótese: vi.clearAllMocks não limpa filas Once; reproduzir), falhas parciais de importação (teste escrito), reorganização visual, suíte final, relatórios, CI, demo.

## Progresso (2026-11-25, noite)
- Benchmarks 100k e 500k concluídos (ver docs/operations/BENCHMARK_2B3.md; versões de script registradas).
- Mocks: causa comprovada (clearAllMocks não limpa filas Once; reprodução em src/test/mock-isolation.test.ts). Correção no setup global (resetAllMocks + restoreAllMocks + unstubAllGlobals). Suíte web: 6 rodadas (3 normais, 3 embaralhadas) aprovadas antes das mudanças de UI.
- Importação: repetição reenvia só o que não foi concluído (estado por aba: campo done).
- Reorganização: cabeçalho com undo/redo e exportação; tabela central; abas Transformar / Cruzar tabelas (sub-abas Super-PROCV, Junção, Comparar, Agrupar) / Mapeamento / Histórico / Gerenciar / Duplicatas / Rastreabilidade. Ações de linha contextuais. Mobile: tabela antes da lateral. Medições antes em docs/operations (evidência em scratchpad/visual).
- E2E completo em execução após reorganização (log %TEMP%\e2e-run-6.log).

