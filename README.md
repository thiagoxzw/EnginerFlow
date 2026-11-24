# EngiFlow

Plataforma pessoal de automação de engenharia industrial. **Uso individual, local** (ADR-0012).

Status: **Fase 1 — Foundation (em verificação)**. Veja [docs/operations/FASE_1_STATUS.md](docs/operations/FASE_1_STATUS.md) para o que foi comprovado e o que ainda não foi.

## Estrutura

```
apps/api             Backend FastAPI (Python 3.12+, SQLAlchemy 2, Alembic)
apps/web             Frontend Next.js 16 (React 19, TypeScript strict, Tailwind v4)
docker-compose.yml   PostgreSQL 17 local (127.0.0.1:5432)
docs/                Documentação de produto, arquitetura e decisões (ADRs)
```

## Pré-requisitos

- Git, Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- Node.js 22 LTS e pnpm 10
- Docker Desktop (para o PostgreSQL do `docker-compose.yml`)

## Configuração

```powershell
Copy-Item .env.example .env   # edite se quiser outra senha local
```

## Subir o banco

```powershell
docker compose up -d postgres
```

## Backend

```powershell
cd apps/api
uv sync
uv run alembic -c alembic.ini upgrade head
uv run python -m engiflow_api.cli create-user --email seu@email.com --name "Seu nome"
uv run uvicorn engiflow_api.main:get_app --factory --host 127.0.0.1 --port 8000
```

A senha é pedida no terminal, sem eco, e precisa ter pelo menos 12 caracteres. O sistema aceita **um único usuário**.

## Frontend

```powershell
cd apps/web
pnpm install
pnpm dev        # http://127.0.0.1:3000
```

O Next encaminha `/api/v1/*` para `ENGIFLOW_API_URL` (padrão `http://127.0.0.1:8000`), então o navegador conversa só com a origem 3000.

## Testes e qualidade

```powershell
cd apps/api
uv run ruff check src tests migrations
uv run mypy
uv run pytest -q

cd ..\web
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

Para rodar os testes da API contra PostgreSQL, defina `ENGIFLOW_TEST_DATABASE_URL`. Sem essa variável, os testes usam SQLite em arquivo temporário.

## Regras do repositório

- Nenhum dado industrial real é versionado. Fixtures são sintéticas.
- Commits seguem Conventional Commits. Merges só com autorização.
- Credenciais ficam no `.env` local (ignorado pelo Git) ou em cofre, nunca no código.

## Documentação

Comece por [docs/PRODUCT_VISION.md](docs/PRODUCT_VISION.md) e [docs/decisions/REVISAO_FASE_0.md](docs/decisions/REVISAO_FASE_0.md).
