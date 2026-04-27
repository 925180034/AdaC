"""SQLAlchemy ORM models — mirrors the DDL in system_design §6.2."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TableRegistry(Base):
    """One row per table uploaded to the data lake."""

    __tablename__ = "table_registry"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','INGESTED','PROFILING','READY','FAILED','ARCHIVED','REJECTED')",
            name="ck_tr_status",
        ),
        Index("ix_tr_tenant_status", "tenant_id", "status"),
        UniqueConstraint("tenant_id", "content_hash", name="ix_tr_content"),
    )

    table_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="default")
    source_system: Mapped[str] = mapped_column(String, nullable=False)
    source_uri: Mapped[str] = mapped_column(String, nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    col_count: Mapped[int | None] = mapped_column(Integer)
    schema_hash: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String)
    uploaded_by: Mapped[str | None] = mapped_column(String)
    uploaded_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")

    columns: Mapped[list[ColumnMetadata]] = relationship(
        "ColumnMetadata", back_populates="table", cascade="all, delete-orphan"
    )


class ColumnMetadata(Base):
    """One row per column of an ingested table."""

    __tablename__ = "column_metadata"
    __table_args__ = (UniqueConstraint("table_id", "ordinal", name="uq_cm_table_ord"),)

    column_id: Mapped[str] = mapped_column(String, primary_key=True)
    table_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("table_registry.table_id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    col_name: Mapped[str] = mapped_column(String, nullable=False)
    col_type: Mapped[str] = mapped_column(String, nullable=False)
    col_description: Mapped[str | None] = mapped_column(Text)
    null_ratio: Mapped[float | None] = mapped_column(Float)
    distinct_ratio: Mapped[float | None] = mapped_column(Float)
    stat_summary: Mapped[str | None] = mapped_column(Text)  # JSON blob
    qdrant_point_id: Mapped[str | None] = mapped_column(String)

    table: Mapped[TableRegistry] = relationship(
        "TableRegistry", back_populates="columns"
    )


class IntegrationTask(Base):
    """One row per /integrate, /discover, or /match request."""

    __tablename__ = "integration_task"
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('INTEGRATE','DISCOVER_ONLY','MATCH_ONLY')",
            name="ck_it_type",
        ),
        Index("ix_it_status", "status", "submitted_at"),
    )

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="default")
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    query_table_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("table_registry.table_id")
    )
    target_table_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("table_registry.table_id")
    )
    plan_config: Mapped[str | None] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String, nullable=False)
    submitted_by: Mapped[str | None] = mapped_column(String)
    submitted_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    artifacts_dir: Mapped[str | None] = mapped_column(String)

    steps: Mapped[list[AgentStep]] = relationship(
        "AgentStep", back_populates="task", cascade="all, delete-orphan"
    )


class AgentStep(Base):
    """Execution trace — one row per agent invocation within a task."""

    __tablename__ = "agent_step"
    __table_args__ = (Index("ix_as_task", "task_id"),)

    step_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("integration_task.task_id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    layer: Mapped[str | None] = mapped_column(String)  # TLCF L1/L2/L3
    input_size: Mapped[int | None] = mapped_column(Integer)
    output_size: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    llm_tokens: Mapped[int | None] = mapped_column(Integer)
    recall_loss: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column()

    task: Mapped[IntegrationTask] = relationship(
        "IntegrationTask", back_populates="steps"
    )


class DiscoveryResult(Base):
    """Ranked candidate tables for a discovery/integrate task."""

    __tablename__ = "discovery_result"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_table: Mapped[str] = mapped_column(
        String, ForeignKey("table_registry.table_id"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    layer_scores: Mapped[str | None] = mapped_column(Text)  # JSON: {l1, l2, l3}


class ColumnMapping(Base):
    """Column-level alignment result for a match/integrate task."""

    __tablename__ = "column_mapping"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "src_column_id", "tgt_column_id", name="uq_cm_pair"
        ),
        CheckConstraint("scenario IN ('SMD','SSD','SLD')", name="ck_cm_scenario"),
    )

    mapping_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    src_column_id: Mapped[str] = mapped_column(
        String, ForeignKey("column_metadata.column_id"), nullable=False
    )
    tgt_column_id: Mapped[str] = mapped_column(
        String, ForeignKey("column_metadata.column_id"), nullable=False
    )
    scenario: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_matched: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # SQLite has no BOOL
    reasoning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class ModelVersion(Base):
    """Tracks active model versions for reproducibility."""

    __tablename__ = "model_version"

    model_key: Mapped[str] = mapped_column(
        String, primary_key=True
    )  # sbert/llm/matcher
    version: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[str | None] = mapped_column(Text)  # JSON
    activated_at: Mapped[datetime] = mapped_column(nullable=False)
