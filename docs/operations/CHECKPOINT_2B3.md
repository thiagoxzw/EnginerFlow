# Checkpoint — Fase 2B (Data Studio completo) — estado final desta execução

Atualizado em 2026-11-25. Leia antes de retomar. Não contém credenciais nem dados reais.

## Estado
- Branch: `feat/fase-2b-3-data-crossing`. PR #4 (draft). **Não fazer merge** sem autorização.
- Fase 2B encerrada. Run #64 (commit `f0a432a`) aprovada. Fase 3 implementada em commits separados, no mesmo branch (de `94e68f7` até o último commit, ver `git log`).
- Último commit da Fase 3 com validação local completa: ver `FASE_2B3_STATUS.md`, seção da Fase 3. O CI do commit mais recente deve ser conferido no GitHub.
- Fase 2B.4 não existe no roadmap oficial: o escopo foi consolidado na Fase 2B (ver `docs/roadmap/FASE_2B_CONSOLIDACAO.md`).
- Demonstrativo: migração `0006_crossing_idempotency` aplicada; dados preservados. Em 2026-11-25 foram removidas logicamente 37 tabelas sintéticas e a cópia sem histórico de `Codigos totus - separado`. Permanece a cópia `6aebaf7e…` (1706 linhas, com o mapeamento v2).
- Não há migração nova na Fase 3.
- Próximos itens (fora desta fase): compressão e retenção de snapshots, e a decisão sobre versionamento incremental, dependendo da medição de crescimento em tabelas grandes. Fase 4 e BOM Manager não foram iniciados.

## Testes (no commit final)
- API: ruff, format, mypy e pytest — ver `FASE_2B3_STATUS.md`.
- Web: typecheck, ESLint, Vitest (80 testes).
- E2E isolado (projeto `engiflow-e2e`, portas 3210/8210/5542): 19/19 aprovados; stack removido ao final.
- Migrações: upgrade → downgrade → upgrade em PostgreSQL 17 limpo.
- Recuperação: backup do demonstrativo restaurado em PostgreSQL isolado (40 tabelas, 2080 linhas de versão, revisão 0005 no dump anterior à 0006).

## Ambientes (ver `LOCAL_SETUP.md`)
- Demonstrativo: projeto `engiflow`, portas 3000/8000/5432, volumes `engiflow_engiflow-pgdata` e `engiflow_engiflow-data`. Em uso.
- Auditoria: projeto `engiflow-audit`, portas 3100/8100/5433. Auxiliar, ainda ativo; pode ser parado (volumes preservados).
- E2E: projeto `engiflow-e2e`. Descartável, removido ao final.
- Benchmark: projeto `engiflow-bench`, porta 5552. Descartável, removido ao final.
- Banco `engiflow_bench` dentro do PostgreSQL demonstrativo (criado em sessão anterior): mantido. Exclusão só com autorização.

## Encerramento administrativo (2026-11-25)
1. **Tabelas sintéticas:** 37 removidas por exclusão lógica pela API (25 derivadas e 12 importações `SYN-*`). Lista e IDs em `backups/removidos-sinteticos-20261125-135151.txt`. Restauráveis pela API (`POST /api/v1/datasets/{id}/restore`).
2. **Cópia duplicada de `Codigos totus - separado`:** conteúdo idêntico (mesmo `content_sha256`, 1706 linhas). A cópia `ab5091de…` (sem histórico) foi excluída logicamente. Preservada `6aebaf7e…`, a mais completa: tem a operação `set_mapping` aplicada e o mapeamento v2 das colunas.
3. **Banco `engiflow_bench`:** removido em sessão anterior, após comprovação de ser exclusivo de benchmark.
4. **Stack `engiflow-audit`:** contêineres, volumes e rede removidos. Verificado em 2026-11-25: sem contêineres, sem volumes `engiflow-audit*` e sem rede `engiflow-audit_default`.
5. **PR #4:** descrição não atualizada por este ambiente (sem autenticação GitHub concedida). Texto em `FASE_2B3_STATUS.md`.

## Limitações (Fase 3)
Ver a seção 7 de `FASE_2B3_STATUS.md`.

## Procedimento de retomada
1. `git status` e `git log --oneline -10` no branch acima.
2. `apps\api\.venv\Scripts\python.exe -m pytest -q -p no:logging` e `pnpm test -- --run` em `apps\web`.
3. E2E isolado: `scripts\e2e\Run-E2E.ps1`.
4. Backup antes de qualquer migração no demonstrativo: `scripts\local\Backup-EngiFlow.ps1`.
