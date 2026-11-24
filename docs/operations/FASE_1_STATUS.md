# Fase 1 — Foundation: status de verificação

Data: 2026-11-24. Branch: `feat/fase-1-foundation`.

Legenda: **Testado** = executado e observado nesta máquina · **Testado em CI** = configurado, não executado ainda · **Planejado** = não feito.

## Entregue

| Item | Status | Evidência |
|---|---|---|
| Monorepo: `apps/api`, `apps/web`, `docker-compose.yml`, `.env.example`, CI | Implementado | arquivos no repositório |
| Health live e readiness (503 quando o banco cai) | Testado | `test_api.py` (health e readiness com banco indisponível) |
| Login, sessão em cookie HttpOnly, logout e sessão expirada | Testado | `test_login_me_dashboard_logout_flow`, `test_expired_session_is_rejected` |
| Senha com Argon2id, mínimo de 12 caracteres, usuário único | Testado | `test_domain_units.py` |
| Erros no formato Problem Details (RFC 9457), inclusive 422 e 401 | Testado | `test_validation_error_uses_problem_format`, `test_dashboard_requires_authentication...` |
| Identificador de correlação em todas as respostas | Testado | `test_correlation_id_is_echoed_and_generated` |
| Auditoria: registro de login (ok/negado) e logout, com mascaramento de segredos | Testado | `test_wrong_password_is_rejected_and_audited`, `test_redact_*` |
| Dashboard com dados reais (versão, banco, atividades dos últimos 7 dias, histórico) | Testado (SQLite) e observado no navegador | captura de tela abaixo |
| Migração inicial (`users`, `sessions`, `audit_logs`) | Testado em SQLite (upgrade, downgrade, upgrade) | ver "Migrações" |
| Interface: login com validação e dashboard | Testado (unitário + build + navegador) | 3 testes de formulário; captura de tela |
| Proxy `/api/v1/*` pelo Next, sem CORS no fluxo normal | Testado | login, me, dashboard e logout via `127.0.0.1:3000` |

## Resultados das verificações

| Verificação | Resultado |
|---|---|
| `pytest` (API, SQLite) | 18 passaram |
| `ruff check` e `ruff format --check` | sem erros |
| `mypy` em modo strict | sem erros (22 arquivos) |
| `pnpm typecheck` (TypeScript strict) | sem erros |
| `pnpm lint` (ESLint, `max-warnings=0`) | sem erros |
| `pnpm test` (Vitest) | 7 passaram (4 cliente HTTP, 3 formulário de login) |
| `pnpm build` (Next 16) | compilou; rotas `/`, `/login` e `/_not-found` |
| `docker compose config` | estrutura válida |
| YAML do CI | válido |
| Migrações Alembic em SQLite | upgrade, downgrade e upgrade sem erros |
| Smoke ponta a ponta (API + web em produção local, SQLite) | login 200, me 200, dashboard 200, senha errada 401 em Problem Details, logout 204, me após logout 401 |

## Não verificado (limitações e bloqueios)

1. **PostgreSQL real — não verificado.** O Docker Desktop não inicia: a virtualização está desligada na BIOS (`VirtualizationFirmwareEnabled: False`) e não há distribuição WSL. Ativar isso exige acesso administrativo ou ao BIOS. Tentei um PostgreSQL embarcado (npm `embedded-postgres` 17.12, sem administrador), mas o bloqueio automático de ações impediu a inicialização do servidor. A suíte de testes, a migração e o CI estão preparados para PostgreSQL (`ENGIFLOW_TEST_DATABASE_URL`), mas **nenhum deles rodou contra PostgreSQL ainda**.
2. **CI no GitHub — não executado.** O workflow foi validado só como YAML. O repositório remoto ainda não existe.
3. **Interface sem testes end-to-end automatizados.** Playwright não foi instalado nesta fase.
4. **Sem gerenciamento de sessão por dispositivo, sem recuperação de senha.** Intencional para uso individual.
5. **Dashboard** mostra apenas indicadores reais disponíveis nesta fase. Projetos, materiais, BOMs e automações aparecerão quando os módulos existirem.
6. **Ainda não existe:** Data Studio, BOM Manager, Material Manager, importação Protheus, agente local, Solid Edge e workflows (fases seguintes).
7. Mensagens de erro HTTP genéricas aparecem com título "Erro HTTP" (não localizado).

## Migrações

- `0001_initial`: `users`, `sessions` (token guardado só como hash SHA-256), `audit_logs` (append-only pela aplicação).

## Próximas etapas

1. Validar PostgreSQL real (via Docker quando houver acesso, ou PostgreSQL local equivalente) e rodar a suíte completa contra ele.
2. Subir o repositório no GitHub privado e confirmar o CI verde.
3. Iniciar Data Studio (Fase 2): importação de XLSX/CSV com mapeamento, zeros à esquerda e encodings.
