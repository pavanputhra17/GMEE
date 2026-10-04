import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.claim import Claim


class RelationshipTypeEnum(str, enum.Enum):
    SIMILAR_TO = "SIMILAR_TO"
    EVOLVED_FROM = "EVOLVED_FROM"


class ClaimClusterRun(Base):
    __tablename__ = "claim_cluster_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    algorithm_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    claims_in_corpus: Mapped[int] = mapped_column(Integer, nullable=False)

    assignments: Mapped[list["ClaimClusterAssignment"]] = relationship(
        "ClaimClusterAssignment", back_populates="cluster_run", cascade="all, delete-orphan"
    )


class ClaimClusterAssignment(Base):
    __tablename__ = "claim_cluster_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claim_cluster_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_label: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_keywords: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    cluster_run: Mapped["ClaimClusterRun"] = relationship("ClaimClusterRun", back_populates="assignments")
    claim: Mapped["Claim"] = relationship("Claim")


class ClaimRelationship(Base):
    __tablename__ = "claim_relationships"

    # One edge per (from, to, type): re-running mutation detection must upsert
    # scores, never accumulate duplicate rows (migration a4c7e1f9b2d6 dedupes
    # pre-existing duplicates before creating this constraint).
    __table_args__ = (
        UniqueConstraint(
            "from_claim_id",
            "to_claim_id",
            "relationship_type",
            name="uq_claim_relationships_edge",
        ),
        Index(
            "uq_claim_relationships_evolved_child",
            "from_claim_id",
            unique=True,
            postgresql_where=text("relationship_type = 'EVOLVED_FROM'"),
            sqlite_where=text("relationship_type = 'EVOLVED_FROM'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    to_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[RelationshipTypeEnum] = mapped_column(
        Enum(RelationshipTypeEnum, name="relationshiptypeenum"),
        nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    mutation_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    from_claim: Mapped["Claim"] = relationship("Claim", foreign_keys=[from_claim_id])
    to_claim: Mapped["Claim"] = relationship("Claim", foreign_keys=[to_claim_id])


class FeedbackVerdict(Base):
    """Human-in-the-loop verdict corrections.

    Users agree or disagree with an engine verdict (optionally submitting the
    band they believe is correct). These rows are the gold labels that power
    the evaluation loop — without them, verdict quality can't be measured.
    """

    __tablename__ = "verdict_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    client_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vote: Mapped[str] = mapped_column(String(8), nullable=False)  # AGREE | DISAGREE
    corrected_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    claim: Mapped["Claim"] = relationship("Claim")


class Alert(Base):
    """Early-warning signals raised by the alert engine.

    Deduplicated by (kind, subject_key): re-evaluation of the same condition
    updates the existing row (last_seen_at) instead of spamming new alerts.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)  # CORROBORATION | CONTRADICTION | MUTATION | SPIKE
    severity: Mapped[str] = mapped_column(String(12), nullable=False, default="INFO")  # INFO | WARNING | CRITICAL
    subject_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
