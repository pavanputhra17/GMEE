"""add verdict columns to claims

Revision ID: b8f4d2c91a55
Revises: a7f2c91d4e10
Create Date: 2026-08-25
"""

import sqlalchemy as sa

from alembic import op

revision = "b8f4d2c91a55"
down_revision = "a7f2c91d4e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("verdict", sa.String(), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("verdict_probability", sa.Float(), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("verdict_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("verdict_evidence", sa.JSON().with_variant(
            sa.dialects.postgresql.JSONB(), "postgresql"
        ), nullable=True),
    )
    op.create_index("ix_claims_verdict", "claims", ["verdict"])


def downgrade() -> None:
    op.drop_index("ix_claims_verdict", table_name="claims")
    op.drop_column("claims", "verdict_evidence")
    op.drop_column("claims", "verdict_rationale")
    op.drop_column("claims", "verdict_probability")
    op.drop_column("claims", "verdict")
