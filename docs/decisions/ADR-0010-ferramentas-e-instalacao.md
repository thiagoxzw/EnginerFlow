# ADR-0010 — Ferramentas de desenvolvimento e instalação condicionada a autorização administrativa

- **Status:** Revisada (2026-11-24) — instalação **pendente de acesso administrativo**

## Situação atual
- Instalado: Git 2.56, Python 3.14, .NET SDK.
- Ausente: Node.js LTS, Docker Desktop, WSL 2, PostgreSQL (será via Docker).
- O responsável **não tem acesso de administrador** nesta máquina. As instalações ficam pendentes até ele obter acesso ou executar a instalação.

## Decisão
- Python: `uv` para ambiente e lock; Ruff; MyPy; Pytest.
- TypeScript: pnpm; ESLint; `tsc --noEmit` em modo strict; Vitest; Playwright quando houver interface a testar.
- PostgreSQL e Redis (se usado) apenas via Docker Compose.
- Antes de qualquer instalação, o assistente verifica o que já existe e **avisa explicitamente** o que será instalado e por quê; instalações que exigem administrador só são executadas com autorização do responsável no momento.

## Motivo
Reduz instalações no sistema e mantém a versão do banco idêntica ao ambiente de teste.
