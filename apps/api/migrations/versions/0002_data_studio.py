"""Data Studio: tabelas importadas (datasets e linhas).

Revision ID: 0002_data_studio
Revises: 0001_initial
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_data_studio"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("file_kind", sa.String(10), nullable=False),
        sa.Column("sheet_key", sa.String(255), nullable=False, server_default=""),
        sa.Column("sheet_name", sa.String(255), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_sha256", "sheet_key", name="uq_datasets_source"),
    )
    op.create_table(
        "dataset_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
    )
    op.create_index("ix_dataset_rows_dataset_row", "dataset_rows", ["dataset_id", "row_number"])


def downgrade() -> None:
    op.drop_index("ix_dataset_rows_dataset_row", table_name="dataset_rows")
    op.drop_table("dataset_rows")
    op.drop_table("datasets")
