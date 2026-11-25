"""Modelos de persistência (SQLAlchemy 2.x). Uso individual: sem organization_id, sem RBAC."""

import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Usuário único da aplicação (ADR-0012)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Session(Base):
    """Sessão de login. Guarda apenas o hash do token, nunca o token."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Registro de operações. Append-only pela aplicação; valores sensíveis são mascarados."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(120), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)


class Dataset(Base):
    """Tabela importada de CSV/XLSX. O arquivo original é guardado com nome gerado (hash)."""

    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("source_sha256", "sheet_key", name="uq_datasets_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(10), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    columns: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Ponteiro para a versão atual (2B.1). Campos columns/mapping/row_count espelham a versão atual.
    current_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("dataset_versions.id", use_alter=True), nullable=True
    )
    current_metadata_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 2B.3: "import" (arquivo original) ou "derived" (resultado de cruzamento, sem arquivo).
    source_kind: Mapped[str] = mapped_column(String(10), nullable=False, default="import")
    derived_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetVersion(Base):
    """Versão materializada de uma tabela. Versão 1 = importação original. Imutável após criada."""

    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "number", name="uq_dataset_versions_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetVersionRow(Base):
    """Linha de uma versão. Valores: string (texto), None (desconhecido); vazio é ""."""

    __tablename__ = "dataset_version_rows"
    __table_args__ = (Index("ix_dataset_version_rows_version_row", "version_id", "row_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[list[str | None]] = mapped_column(JSON, nullable=False)


class DatasetMetadataVersion(Base):
    """Metadados de uma tabela (colunas, mapeamento, cabeçalho). Cadeia própria, imutável.

    `version_id` é a versão de DADOS que esta descrição acompanha. Várias versões de metadados
    podem apontar para a mesma versão de dados (mudança só de mapeamento não copia linhas).
    """

    __tablename__ = "dataset_metadata_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "number", name="uq_dataset_metadata_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_metadata_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    columns: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    mapping: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    header_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_definition_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="sistema")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetTemplate(Base):
    """Template reutilizável de mapeamento (campos canônicos -> nomes de colunas)."""

    __tablename__ = "dataset_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    definition: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetOperation(Base):
    """Histórico de operações. Nunca apagado: desfazer muda o status para 'undone'."""

    __tablename__ = "dataset_operations"
    __table_args__ = (
        UniqueConstraint("dataset_id", "seq", name="uq_dataset_operations_seq"),
        UniqueConstraint("dataset_id", "idempotency_key", name="uq_dataset_operations_idem"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    before_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    after_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    before_metadata_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    after_metadata_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rows_affected: Mapped[int] = mapped_column(Integer, nullable=False)
    cells_changed: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DatasetPreview(Base):
    """Prévia de operação. Consumida uma única vez e com validade."""

    __tablename__ = "dataset_previews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    base_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    base_metadata_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    after_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    after_metadata_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rows_affected: Mapped[int] = mapped_column(Integer, nullable=False)
    cells_changed: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrossingRun(Base):
    """Execução de cruzamento (2B.3) que gerou uma tabela derivada. Imutável após criada.

    Congela o que foi usado: parâmetros canônicos, política, chaves, contagens e o hash do
    resultado. Não depende de edições posteriores das origens.
    """

    __tablename__ = "crossing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    operation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    params_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrossingRunSource(Base):
    """Tabela de origem de uma execução, com as versões exatas usadas (congeladas)."""

    __tablename__ = "crossing_run_sources"
    __table_args__ = (UniqueConstraint("run_id", "role", name="uq_crossing_run_sources_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crossing_runs.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # left | right
    dataset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    metadata_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
