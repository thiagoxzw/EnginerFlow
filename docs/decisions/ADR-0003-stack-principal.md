# ADR-0003 — Stack: Python/FastAPI no backend e Next.js/TypeScript no frontend

- **Status:** Revisada (2026-11-24) — mantida, aguarda aprovação
- **Pedido do responsável:** manter Next.js, TypeScript, Python, FastAPI e PostgreSQL.

## Decisão
- Backend: Python (versão a fixar na instalação; a máquina tem 3.14), FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
- Frontend: Next.js, React, TypeScript `strict`, Tailwind, shadcn/ui, TanStack Query e Table, React Hook Form, Zod. React Flow e Recharts só quando a funcionalidade existir.
- Contrato OpenAPI gerado pelo FastAPI; cliente TypeScript gerado em `packages/api-client` quando houver mais de um consumidor (com um só, pode-se consumir direto; decisão na Fase 1).
- Dependências adicionadas apenas quando houver uso prático.

## Motivo
Processamento de planilhas (Pandas, OpenPyXL, RapidFuzz) e integração Windows (PyWin32) são maduros em Python. Next.js dá interface moderna para uso diário.

## Alternativa avaliada
Tudo em TypeScript: descartada porque duplicaria o processamento de dados e o acesso COM ficaria mais difícil.
