"""add alerts table for early-warning engine

Revision ID: e8c2f4a6b1d3
Revises: d5f8a1c3e7b9
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e8c2f4a6b1d3"
down_revision = "d5f8a1c3e7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False, server_default="INFO"),
        sa.Column("subject_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alerts_kind", "alerts", ["kind"])
    op.create_unique_constraint(
        "uq_alerts_kind_subject", "alerts", ["kind", "subject_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_alerts_kind_subject", "alerts", type_="unique")
    op.drop_index("ix_alerts_kind", table_name="alerts")
    op.drop_table("alerts")