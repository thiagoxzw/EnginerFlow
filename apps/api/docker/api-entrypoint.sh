#!/bin/sh
# Aplica as migrações antes de subir a API. Falha se a migração falhar (sem subir versão incompleta).
set -eu
alembic -c alembic.ini upgrade head
exec uvicorn engiflow_api.main:create_app --factory --host 0.0.0.0 --port 8000
