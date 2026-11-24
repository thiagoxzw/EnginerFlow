# Changelog

Formato: Keep a Changelog. Versionamento: Semantic Versioning (ainda sem versão publicada).

## [Unreleased]

### Adicionado
- Fase 0: documentação de visão, PRD, arquitetura e decisões (ADR-0001 a ADR-0012), revisadas para uso individual.
- Fase 1 (em verificação): backend FastAPI com health e readiness; login de usuário único com sessão em cookie HttpOnly; logout; auditoria de login e logout; dashboard com dados reais; erros em Problem Details; correlação de requisições; migração inicial; frontend Next.js com login e dashboard; `docker-compose.yml` com PostgreSQL; CI no GitHub Actions.

### Alterado
- CI: `actions/checkout` v4 → v6, `astral-sh/setup-uv` v6 → v7, `actions/setup-node` v4 → v6 e `pnpm/action-setup` v4 → v6. As novas versões rodam em Node 24, eliminando o aviso de depreciação do Node 20. Parâmetros mantidos (cache do uv, `cache-dependency-glob`, `version` do pnpm, cache do pnpm). Node 22 do build web e comandos de teste inalterados.

### Pendente de verificação
- Execução contra PostgreSQL real (bloqueada: Docker sem virtualização habilitada nesta máquina).
