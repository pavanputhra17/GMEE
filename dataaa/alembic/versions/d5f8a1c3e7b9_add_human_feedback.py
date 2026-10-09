"""add human verdict feedback table

Revision ID: d5f8a1c3e7b9
Revises: b8f4d2c91a55
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d5f8a1c3e7b9"
down_revision = "b8f4d2c91a55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verdict_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_hash", sa.String(64), nullable=False),
        sa.Column("vote", sa.String(8), nullable=False),
        sa.Column("corrected_verdict", sa.String(32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_verdict_feedback_claim_id", "verdict_feedback", ["claim_id"])
    op.create_index("ix_verdict_feedback_client_hash", "verdict_feedback", ["client_hash"])
    op.create_unique_constraint(
        "uq_verdict_feedback_claim_client",
        "verdict_feedback",
        ["claim_id", "client_hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_verdict_feedback_claim_client", "verdict_feedback", type_="unique")
    op.drop_index("ix_verdict_feedback_client_hash", table_name="verdict_feedback")
    op.drop_index("ix_verdict_feedback_claim_id", table_name="verdict_feedback")
    op.drop_table("verdict_feedback")