import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    to_claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[RelationshipTypeEnum] = mapped_column(
        Enum(RelationshipTypeEnum, name="relationshiptypeenum"),
        nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    from_claim: Mapped["Claim"] = relationship("Claim", foreign_keys=[from_claim_id])
    to_claim: Mapped["Claim"] = relationship("Claim", foreign_keys=[to_claim_id])
