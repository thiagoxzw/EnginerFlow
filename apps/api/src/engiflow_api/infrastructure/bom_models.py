"""Modelos do BOM Manager (Fase 4). Mesmo `Base` dos demais modelos, em tabelas próprias.

Revisões são imutáveis: edições criam nova revisão, e a anterior permanece. Quantidades e códigos
são texto, para preservar zeros à esquerda, caracteres especiais e valores desconhecidos (NULL).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from engiflow_api.infrastructure.models import Base, _uuid


class BomStructure(Base):
    """Estrutura de materiais. A revisão atual é um ponteiro; o histórico fica nas revisões."""

    __tablename__ = "bom_structures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BomRevision(Base):
    """Revisão: foto imutável das linhas, com a origem e o mapeamento usados."""

    __tablename__ = "bom_revisions"
    __table_args__ = (UniqueConstraint("structure_id", "number", name="uq_bom_revisions_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    structure_id: Mapped[str] = mapped_column(
        ForeignKey("bom_structures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    parent_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="explicit")
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BomLine(Base):
    """Linha de uma revisão. Códigos e quantidades em texto: nada é convertido na gravação."""

    __tablename__ = "bom_lines"
    __table_args__ = (Index("ix_bom_lines_revision_parent", "revision_id", "parent_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("bom_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    child_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qty_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rev: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    part_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    inferred_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class BomKit(Base):
    """Kit de montagem: subconjuntos e quantidade por kit, dentro de uma estrutura."""

    __tablename__ = "bom_kits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    structure_id: Mapped[str] = mapped_column(
        ForeignKey("bom_structures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    parts: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
