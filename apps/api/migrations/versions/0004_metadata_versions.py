"""Versionamento de metadados, mapeamentos e templates (2B.2).

- Metadados passam a ter cadeia própria (`dataset_metadata_versions`): número, pai, cabeçalho,
  hash de metadados e referência a template. Cada versão de dados ganha a sua primeira versão
  de metadados (a que já existia), preservando o histórico.
- Operações e prévias registram o estado de metadados antes/depois (colunas novas, nulas em
  registros antigos e preenchidas a partir da versão de dados correspondente).
- Hash de conteúdo de dados passa a cobrir só as linhas (`rows_sha256`); os valores antigos são
  recalculados. O hash de metadados é novo.
- Tabelas ganham `current_metadata_version_id` e exclusão lógica (`deleted_at`).
- Nova tabela `dataset_templates`.

Downgrade: restaura o esquema anterior mantendo a versão de metadados mais recente de cada
versão de dados. Histórico detalhado de metadados não é recuperável nesse sentido; os hashes
recalculados não voltam aos valores anteriores (ver docs/operations/FASE_2B2_STATUS.md).

Revision ID: 0004_metadata_versions
Revises: 0003_dataset_versions
Create Date: 2026-11-24
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from engiflow_api.domain.canonical import metadata_sha256, rows_sha256

revision: str = "0004_metadata_versions"
down_revision: str | None = "0003_dataset_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH = 2_000


def upgrade() -> None:
    bind = op.get_bind()
    now = dt.datetime.now(dt.UTC)

    op.create_table(
        "dataset_metadata_versions__new",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("parent_metadata_version_id", sa.String(36), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("header_row", sa.Integer(), nullable=True),
        sa.Column("metadata_sha256", sa.String(64), nullable=False),
        sa.Column("template_id", sa.String(36), nullable=True),
        sa.Column("template_definition_version", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(120), nullable=False, server_default="sistema"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("dataset_id", "number", name="uq_dataset_metadata_number"),
    )

    old_meta = sa.table(
        "dataset_metadata_versions",
        sa.column("id", sa.String),
        sa.column("version_id", sa.String),
        sa.column("columns", sa.JSON),
        sa.column("mapping", sa.JSON),
    )
    versions = sa.table(
        "dataset_versions",
        sa.column("id", sa.String),
        sa.column("dataset_id", sa.String),
        sa.column("content_sha256", sa.String),
    )
    version_rows = sa.table(
        "dataset_version_rows",
        sa.column("version_id", sa.String),
        sa.column("row_number", sa.Integer),
        sa.column("values", sa.JSON),
    )
    new_meta = sa.table(
        "dataset_metadata_versions__new",
        sa.column("id", sa.String),
        sa.column("dataset_id", sa.String),
        sa.column("version_id", sa.String),
        sa.column("number", sa.Integer),
        sa.column("parent_metadata_version_id", sa.String),
        sa.column("columns", sa.JSON),
        sa.column("mapping", sa.JSON),
        sa.column("header_row", sa.Integer),
        sa.column("metadata_sha256", sa.String),
        sa.column("actor", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    # 1) Metadados existentes viram a primeira versão de metadados de cada versão de dados.
    meta_by_version: dict[str, str] = {}
    for meta_id, version_id, columns, mapping in bind.execute(
        sa.select(old_meta.c.id, old_meta.c.version_id, old_meta.c.columns, old_meta.c.mapping)
    ).all():
        dataset_id = bind.execute(
            sa.select(versions.c.dataset_id).where(versions.c.id == version_id)
        ).scalar_one()
        digest = metadata_sha256(list(columns), dict(mapping or {}), None)
        bind.execute(
            new_meta.insert().values(
                id=meta_id,
                dataset_id=dataset_id,
                version_id=version_id,
                number=1,
                parent_metadata_version_id=None,
                columns=list(columns),
                mapping=dict(mapping or {}),
                header_row=None,
                metadata_sha256=digest,
                actor="sistema",
                created_at=now,
            )
        )
        meta_by_version[version_id] = meta_id

    # 2) Hash de dados passa a cobrir só as linhas.
    for version_id in list(meta_by_version):
        rows = (
            bind.execute(
                sa.select(version_rows.c["values"])
                .where(version_rows.c.version_id == version_id)
                .order_by(version_rows.c.row_number)
            )
            .scalars()
            .all()
        )
        digest = rows_sha256([list(r) for r in rows])
        bind.execute(
            versions.update().where(versions.c.id == version_id).values(content_sha256=digest)
        )

    # 3) Troca a tabela de metadados pela nova (mesmo nome final).
    op.drop_table("dataset_metadata_versions")
    op.rename_table("dataset_metadata_versions__new", "dataset_metadata_versions")
    op.create_index(
        "ix_dataset_metadata_versions_version", "dataset_metadata_versions", ["version_id"]
    )

    # 4) Colunas novas em datasets, operações e prévias.
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("current_metadata_version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("dataset_operations") as batch:
        batch.add_column(sa.Column("before_metadata_version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("after_metadata_version_id", sa.String(36), nullable=True))
    with op.batch_alter_table("dataset_previews") as batch:
        batch.add_column(sa.Column("base_metadata_version_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("after_metadata_sha256", sa.String(64), nullable=True))

    datasets = sa.table(
        "datasets",
        sa.column("id", sa.String),
        sa.column("current_version_id", sa.String),
        sa.column("current_metadata_version_id", sa.String),
    )
    operations = sa.table(
        "dataset_operations",
        sa.column("id", sa.String),
        sa.column("before_version_id", sa.String),
        sa.column("after_version_id", sa.String),
        sa.column("before_metadata_version_id", sa.String),
        sa.column("after_metadata_version_id", sa.String),
    )
    for dataset_id, current_version_id in bind.execute(
        sa.select(datasets.c.id, datasets.c.current_version_id)
    ).all():
        if current_version_id in meta_by_version:
            bind.execute(
                datasets.update()
                .where(datasets.c.id == dataset_id)
                .values(current_metadata_version_id=meta_by_version[current_version_id])
            )
    for op_id, before_v, after_v in bind.execute(
        sa.select(operations.c.id, operations.c.before_version_id, operations.c.after_version_id)
    ).all():
        bind.execute(
            operations.update()
            .where(operations.c.id == op_id)
            .values(
                before_metadata_version_id=meta_by_version.get(before_v),
                after_metadata_version_id=meta_by_version.get(after_v),
            )
        )

    # 5) Templates de mapeamento.
    op.create_table(
        "dataset_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("dataset_templates")
    with op.batch_alter_table("dataset_previews") as batch:
        batch.drop_column("after_metadata_sha256")
        batch.drop_column("base_metadata_version_id")
    with op.batch_alter_table("dataset_operations") as batch:
        batch.drop_column("after_metadata_version_id")
        batch.drop_column("before_metadata_version_id")
    with op.batch_alter_table("datasets") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("current_metadata_version_id")

    # Restaura a tabela de metadados anterior, mantendo a versão mais recente por versão de dados.
    op.create_table(
        "dataset_metadata_versions__old",
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
    bind.execute(
        sa.text(
            "INSERT INTO dataset_metadata_versions__old (id, version_id, columns, mapping) "
            "SELECT m.id, m.version_id, m.columns, m.mapping FROM dataset_metadata_versions m "
            "WHERE m.number = (SELECT MAX(m2.number) FROM dataset_metadata_versions m2 "
            "WHERE m2.version_id = m.version_id)"
        )
    )
    op.drop_table("dataset_metadata_versions")
    op.rename_table("dataset_metadata_versions__old", "dataset_metadata_versions")
