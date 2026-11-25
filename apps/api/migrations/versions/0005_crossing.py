"""Cruzamento entre tabelas (2B.3): execuções, origens congeladas e origem das tabelas.

- `crossing_runs`: execução que gerou uma tabela derivada (parâmetros, política, contagens, hash).
- `crossing_run_sources`: versões de dados e de metadados de cada origem, congeladas.
- `datasets.source_kind` ('import' | 'derived') e `datasets.derived_run_id`.

Tabelas existentes não são reescritas. Downgrade remove apenas o que esta revisão criou.

Revision ID: 0005_crossing
Revises: 0004_metadata_versions
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_crossing"
down_revision: str | None = "0004_metadata_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crossing_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("operation_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("params_sha256", sa.String(64), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("result_dataset_id", sa.String(36), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "crossing_run_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("crossing_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("dataset_name", sa.String(255), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("metadata_version_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("run_id", "role", name="uq_crossing_run_sources_role"),
    )
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(
            sa.Column("source_kind", sa.String(10), nullable=False, server_default="import")
        )
        batch.add_column(sa.Column("derived_run_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.drop_column("derived_run_id")
        batch.drop_column("source_kind")
    op.drop_table("crossing_run_sources")
    op.drop_table("crossing_runs")
