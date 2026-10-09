import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class EvalPair(Base):
    """One gold-standard claim pair awaiting (or holding) human labels.

    Similarity metadata (sim_score, bucket) is stored for stratification and
    analysis but MUST NOT be exposed by the labeling API — annotators see
    only the two claim texts, so their judgement stays unbiased.
    """

    __tablename__ = "eval_pairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sim_score: Mapped[float] = mapped_column(Float, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    labels: Mapped[list["EvalPairLabel"]] = relationship(
        "EvalPairLabel", back_populates="pair", cascade="all, delete-orphan"
    )


class EvalPairLabel(Base):
    """A single annotator's label for a pair (one per annotator per pair)."""

    __tablename__ = "eval_pair_labels"
    __table_args__ = (UniqueConstraint("pair_id", "annotator", name="uq_eval_label_pair_annotator"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eval_pairs.id", ondelete="CASCADE"), nullable=False, index=True)
    annotator: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False)  # SAME_STORY | EVOLVED | DISTINCT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pair: Mapped["EvalPair"] = relationship("EvalPair", back_populates="labels")