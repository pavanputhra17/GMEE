import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


def _canonical_pair_key(context: Any) -> str:
    values = context.get_current_parameters()
    a, b = sorted(str(uuid.UUID(str(values[name]))) for name in ("claim_a_id", "claim_b_id"))
    return f"{a}:{b}"


class EvalPair(Base):
    """One gold-standard claim pair awaiting (or holding) human labels.

    Similarity metadata (sim_score, bucket) is stored for stratification and
    analysis but MUST NOT be exposed by the labeling API — annotators see
    only the two claim texts, so their judgement stays unbiased.
    """

    __tablename__ = "eval_pairs"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_eval_pairs_canonical_key"),
        CheckConstraint("split IN ('unassigned', 'train', 'dev', 'test')", name="ck_eval_pair_split"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sim_score: Mapped[float] = mapped_column(Float, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Duplicate historical pairs retain NULL keys; new pairs always get a canonical key.
    canonical_key: Mapped[str | None] = mapped_column(String(73), default=_canonical_pair_key, nullable=True)
    split: Mapped[str] = mapped_column(String(16), default="unassigned", server_default="unassigned", nullable=False, index=True)
    event_group: Mapped[str] = mapped_column(String(128), default="unassigned", server_default="unassigned", nullable=False, index=True)
    sampling_provenance: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict, server_default="{}", nullable=False)

    labels: Mapped[list["EvalPairLabel"]] = relationship(
        "EvalPairLabel", back_populates="pair", cascade="all, delete-orphan"
    )


class EvalPairLabel(Base):
    """Current vote per identity/origin, with append-only prior revisions.

    A claimed human identity in old data is not authenticated evidence. Defaults
    deliberately remain legacy; only the authenticated API writes human votes.
    """

    __tablename__ = "eval_pair_labels"
    __table_args__ = (
        UniqueConstraint("pair_id", "annotator", "origin", name="uq_eval_label_pair_annotator_origin"),
        CheckConstraint("origin IN ('human', 'automatic', 'legacy', 'test')", name="ck_eval_label_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eval_pairs.id", ondelete="CASCADE"), nullable=False, index=True)
    annotator: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(16), nullable=False)  # SAME_STORY | EVOLVED | DISTINCT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), default="legacy", server_default="legacy", nullable=False, index=True)
    annotator_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", name="fk_eval_label_user"), nullable=True, index=True)
    mutation_types: Mapped[list[str] | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict, server_default="{}", nullable=False)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=list, server_default="[]", nullable=False)

    pair: Mapped["EvalPair"] = relationship("EvalPair", back_populates="labels")