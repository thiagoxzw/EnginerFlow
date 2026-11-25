# Backend EngiFlow (FastAPI). Imagem de execução local; não exposta publicamente pelo compose.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.8.22

WORKDIR /app

# Dependências primeiro (cache de camadas), depois o código.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --locked --no-dev

COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
RUN chmod +x /usr/local/bin/api-entrypoint.sh

RUN useradd --create-home --uid 10001 engiflow && mkdir -p /app/data && chown -R engiflow /app/data
USER engiflow

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/api-entrypoint.sh"]
