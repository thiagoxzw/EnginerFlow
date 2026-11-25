"""BOM Manager (Fase 4): estruturas, revisões imutáveis, linhas e kits.

Somente criação de tabelas novas. Nenhuma tabela existente é alterada ou reescrita; o downgrade
remove apenas as tabelas criadas aqui.

Revision ID: 0007_bom_manager
Revises: 0006_crossing_idempotency
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_bom_manager"
down_revision: str | None = "0006_crossing_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bom_structures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("current_revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "bom_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "structure_id",
            sa.String(36),
            sa.ForeignKey("bom_structures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("label", sa.String(160), nullable=False, server_default=""),
        sa.Column("parent_revision_id", sa.String(36), nullable=True),
        sa.Column("source_dataset_id", sa.String(36), nullable=True),
        sa.Column("source_version_id", sa.String(36), nullable=True),
        sa.Column("mapping", sa.JSON, nullable=False),
        sa.Column("mode", sa.String(10), nullable=False, server_default="explicit"),
        sa.Column("line_count", sa.Integer, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("structure_id", "number", name="uq_bom_revisions_number"),
    )
    op.create_index("ix_bom_revisions_structure_id", "bom_revisions", ["structure_id"])
    op.create_table(
        "bom_lines",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("bom_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("source_row", sa.Integer, nullable=True),
        sa.Column("parent_code", sa.String(255), nullable=True),
        sa.Column("child_code", sa.String(255), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("qty_raw", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("rev", sa.String(64), nullable=True),
        sa.Column("position", sa.String(64), nullable=True),
        sa.Column("level", sa.Integer, nullable=True),
        sa.Column("alt_code", sa.String(255), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("part_number", sa.String(255), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("inferred_parent", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_bom_lines_revision_id", "bom_lines", ["revision_id"])
    op.create_index("ix_bom_lines_revision_parent", "bom_lines", ["revision_id", "parent_code"])
    op.create_table(
        "bom_kits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "structure_id",
            sa.String(36),
            sa.ForeignKey("bom_structures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("parts", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bom_kits_structure_id", "bom_kits", ["structure_id"])


def downgrade() -> None:
    op.drop_index("ix_bom_kits_structure_id", table_name="bom_kits")
    op.drop_table("bom_kits")
    op.drop_index("ix_bom_lines_revision_parent", table_name="bom_lines")
    op.drop_index("ix_bom_lines_revision_id", table_name="bom_lines")
    op.drop_table("bom_lines")
    op.drop_index("ix_bom_revisions_structure_id", table_name="bom_revisions")
    op.drop_table("bom_revisions")
    op.drop_table("bom_structures")
