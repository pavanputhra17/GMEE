"""Durable pipeline job records (gmee03).

One row per collection/preprocessing/NLP/evolution run, whether scheduled or
manually triggered. Rows survive process restarts, so job state is no longer
worker-local memory. A partial unique index allows at most ONE ``running``
row per job type: a second concurrent trigger fails fast instead of racing.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class JobStatusEnum(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    abandoned = "abandoned"  # lease expired without a terminal update (crash)


class JobTypeEnum(str, enum.Enum):
    collection = "collection"
    preprocessing = "preprocessing"
    nlp = "nlp"
    evolution = "evolution"


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatusEnum.running.value)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # scheduler | manual | chained
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    # Sanitized: exception class + bounded message, never stack traces/secrets.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_pipeline_jobs_one_running",
            "job_type",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index("ix_pipeline_jobs_type_started", "job_type", "started_at"),
    )
