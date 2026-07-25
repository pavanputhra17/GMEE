import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ProcessingStatusEnum(str, enum.Enum):
    raw = "raw"
    processing = "processing"
    processed = "processed"
    skipped_non_english = "skipped_non_english"
    failed = "failed"


class NLPStatusEnum(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, server_default="{}")
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)

    # Preprocessing fields
    processing_status: Mapped[ProcessingStatusEnum] = mapped_column(
        Enum(ProcessingStatusEnum, name="processingstatusenum"), 
        nullable=False, 
        server_default="raw"
    )
    cleaned_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_article_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    word_count: Mapped[int | None] = mapped_column(nullable=True)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # NLP fields
    nlp_status: Mapped[NLPStatusEnum] = mapped_column(
        Enum(NLPStatusEnum, name="nlpstatusenum"),
        nullable=False,
        server_default="pending"
    )

    source: Mapped["Source"] = relationship("Source", back_populates="articles")
