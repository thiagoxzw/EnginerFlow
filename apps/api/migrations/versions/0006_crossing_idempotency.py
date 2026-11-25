"""Idempotência das tabelas derivadas (2B.3): chave única por execução de cruzamento.

- `crossing_runs.idempotency_key`: chave enviada pelo cliente (Idempotency-Key), única quando presente.
  Linhas antigas ficam com NULL (sem chave), e NULLs não conflitam entre si.

Tabelas existentes não são reescritas. Downgrade remove apenas a coluna e o índice criados aqui.

Revision ID: 0006_crossing_idempotency
Revises: 0005_crossing
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_crossing_idempotency"
down_revision: str | None = "0005_crossing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("crossing_runs") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(128), nullable=True))
        batch.create_unique_constraint("uq_crossing_runs_idempotency_key", ["idempotency_key"])


def downgrade() -> None:
    with op.batch_alter_table("crossing_runs") as batch:
        batch.drop_constraint("uq_crossing_runs_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
