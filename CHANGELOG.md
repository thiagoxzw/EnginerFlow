# Changelog

Formato: Keep a Changelog. Versionamento: Semantic Versioning (ainda sem versão publicada).

## [Unreleased]

### Adicionado
- Fase 0: documentação de visão, PRD, arquitetura e decisões (ADR-0001 a ADR-0012), revisadas para uso individual.
- Fase 1 (em verificação): backend FastAPI com health e readiness; login de usuário único com sessão em cookie HttpOnly; logout; auditoria de login e logout; dashboard com dados reais; erros em Problem Details; correlação de requisições; migração inicial; frontend Next.js com login e dashboard; `docker-compose.yml` com PostgreSQL; CI no GitHub Actions.

### Pendente de verificação
- Execução contra PostgreSQL real (bloqueada: Docker sem virtualização habilitada nesta máquina).
- Execução do workflow de CI no GitHub (repositório remoto ainda não criado).
