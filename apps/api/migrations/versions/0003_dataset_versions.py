"""Versionamento de tabelas (2B.1): versões, linhas por versão, metadados, operações e prévias.

Migra os dados da 2A sem perda:
- cada tabela importada vira a versão 1 (id da versão = id da tabela);
- as linhas de dataset_rows são copiadas para dataset_version_rows;
- o hash canônico da versão 1 é calculado a partir das linhas copiadas;
- colunas e mapeamento viram a primeira linha de dataset_metadata_versions.

Revision ID: 0003_dataset_versions
Revises: 0002_data_studio
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from engiflow_api.domain.canonical import content_sha256

revision: str = "0003_dataset_versions"
down_revision: str | None = "0002_data_studio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH = 2_000


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dataset_id", "number", name="uq_dataset_versions_number"),
    )
    op.create_table(
        "dataset_version_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_dataset_version_rows_version_row", "dataset_version_rows", ["version_id", "row_number"]
    )
    op.create_table(
        "dataset_metadata_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
    )
    op.create_table(
        "dataset_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("code_version", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("params_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("before_version_id", sa.String(36), nullable=False),
        sa.Column("after_version_id", sa.String(36), nullable=False),
        sa.Column("rows_affected", sa.Integer(), nullable=False),
        sa.Column("cells_changed", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dataset_id", "seq", name="uq_dataset_operations_seq"),
        sa.UniqueConstraint("dataset_id", "idempotency_key", name="uq_dataset_operations_idem"),
    )
    op.create_table(
        "dataset_previews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("base_version_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("code_version", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("params_sha256", sa.String(64), nullable=False),
        sa.Column("after_content_sha256", sa.String(64), nullable=False),
        sa.Column("rows_affected", sa.Integer(), nullable=False),
        sa.Column("cells_changed", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("current_version_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_datasets_current_version", "dataset_versions", ["current_version_id"], ["id"]
        )

    _migrate_existing_datasets()

    op.drop_index("ix_dataset_rows_dataset_row", table_name="dataset_rows")
    op.drop_table("dataset_rows")


def _migrate_existing_datasets() -> None:
    bind = op.get_bind()
    datasets = sa.table(
        "datasets",
        sa.column("id", sa.String),
        sa.column("columns", sa.JSON),
        sa.column("mapping", sa.JSON),
        sa.column("current_version_id", sa.String),
    )
    versions = sa.table(
        "dataset_versions",
        sa.column("id", sa.String),
        sa.column("dataset_id", sa.String),
        sa.column("number", sa.Integer),
        sa.column("parent_version_id", sa.String),
        sa.column("row_count", sa.Integer),
        sa.column("content_sha256", sa.String),
        sa.column("schema_version", sa.Integer),
        sa.column("pinned", sa.Boolean),
    )
    version_rows = sa.table(
        "dataset_version_rows",
        sa.column("version_id", sa.String),
        sa.column("row_number", sa.Integer),
        sa.column("values", sa.JSON),
    )
    metadata = sa.table(
        "dataset_metadata_versions",
        sa.column("id", sa.String),
        sa.column("version_id", sa.String),
        sa.column("columns", sa.JSON),
        sa.column("mapping", sa.JSON),
    )
    old_rows = sa.table(
        "dataset_rows",
        sa.column("dataset_id", sa.String),
        sa.column("row_number", sa.Integer),
        sa.column("values", sa.JSON),
    )

    for dataset_id, columns, mapping in bind.execute(
        sa.select(datasets.c.id, datasets.c["columns"], datasets.c.mapping)
    ).all():
        ordered = bind.execute(
            sa.select(old_rows.c.row_number, old_rows.c["values"])
            .where(old_rows.c.dataset_id == dataset_id)
            .order_by(old_rows.c.row_number)
        ).all()
        values_only = [list(values) for _, values in ordered]
        digest = content_sha256(list(columns), values_only)
        bind.execute(
            versions.insert().values(
                id=dataset_id,
                dataset_id=dataset_id,
                number=1,
                parent_version_id=None,
                row_count=len(values_only),
                content_sha256=digest,
                schema_version=1,
                pinned=False,
            )
        )
        for start in range(0, len(ordered), _BATCH):
            chunk = ordered[start : start + _BATCH]
            bind.execute(
                version_rows.insert(),
                [
                    {"version_id": dataset_id, "row_number": number, "values": list(values)}
                    for number, values in chunk
                ],
            )
        bind.execute(
            metadata.insert().values(
                id=f"meta-{dataset_id}",
                version_id=dataset_id,
                columns=list(columns),
                mapping=dict(mapping or {}),
            )
        )
        bind.execute(
            datasets.update()
            .where(datasets.c.id == dataset_id)
            .values(current_version_id=dataset_id)
        )


def downgrade() -> None:
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
    bind = op.get_bind()
    bind.execute(
        sa.text(
            'INSERT INTO dataset_rows (dataset_id, row_number, "values") '
            'SELECT d.id, vr.row_number, vr."values" FROM datasets d '
            "JOIN dataset_version_rows vr ON vr.version_id = d.current_version_id"
        )
    )
    op.drop_table("dataset_previews")
    op.drop_table("dataset_operations")
    op.drop_table("dataset_metadata_versions")
    op.drop_index("ix_dataset_version_rows_version_row", table_name="dataset_version_rows")
    op.drop_table("dataset_version_rows")
    with op.batch_alter_table("datasets") as batch:
        batch.drop_constraint("fk_datasets_current_version", type_="foreignkey")
        batch.drop_column("current_version_id")
    op.drop_table("dataset_versions")
