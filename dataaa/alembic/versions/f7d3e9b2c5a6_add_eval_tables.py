"""gold-standard evaluation tables (eval_pairs, eval_pair_labels)

Revision ID: f7d3e9b2c5a6
Revises: e8c2f4a6b1d3
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f7d3e9b2c5a6"
down_revision = "e8c2f4a6b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "claim_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(16), nullable=False),
        sa.Column("sim_score", sa.Float(), nullable=False),
        sa.Column(
            "sampled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_eval_pairs_claim_a_id", "eval_pairs", ["claim_a_id"])
    op.create_index("ix_eval_pairs_claim_b_id", "eval_pairs", ["claim_b_id"])
    op.create_index("ix_eval_pairs_bucket", "eval_pairs", ["bucket"])

    op.create_table(
        "eval_pair_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pair_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_pairs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("annotator", sa.String(64), nullable=False),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("pair_id", "annotator", name="uq_eval_label_pair_annotator"),
    )
    op.create_index("ix_eval_pair_labels_pair_id", "eval_pair_labels", ["pair_id"])
    op.create_index("ix_eval_pair_labels_annotator", "eval_pair_labels", ["annotator"])


def downgrade() -> None:
    op.drop_index("ix_eval_pair_labels_annotator", table_name="eval_pair_labels")
    op.drop_index("ix_eval_pair_labels_pair_id", table_name="eval_pair_labels")
    op.drop_table("eval_pair_labels")
    op.drop_index("ix_eval_pairs_bucket", table_name="eval_pairs")
    op.drop_index("ix_eval_pairs_claim_b_id", table_name="eval_pairs")
    op.drop_index("ix_eval_pairs_claim_a_id", table_name="eval_pairs")
    op.drop_table("eval_pairs")