"""Add typed mutation evidence and enforce one evolution parent per child.

Revision ID: gmee01
Revises: b7d2f4a8c1e9

Historical evidence remains NULL until a detector run re-evaluates it. If
historical children have multiple parents, upgrade fails with an actionable
error instead of silently discarding or reclassifying historical edges.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "gmee01"
down_revision = "b7d2f4a8c1e9"
branch_labels = None
depends_on = None

_PARENT_PREFLIGHT = """
DO $$
BEGIN
    IF EXISTS (
        SELECT from_claim_id
        FROM claim_relationships
        WHERE relationship_type = 'EVOLVED_FROM'
        GROUP BY from_claim_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'gmee01: historical claims have multiple EVOLVED_FROM parents; resolve conflicting parents explicitly before retrying. No historical relationships were removed.';
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_PARENT_PREFLIGHT)
    op.add_column(
        "claim_relationships",
        sa.Column(
            "mutation_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_index(
        "uq_claim_relationships_evolved_child",
        "claim_relationships",
        ["from_claim_id"],
        unique=True,
        postgresql_where=sa.text("relationship_type = 'EVOLVED_FROM'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_claim_relationships_evolved_child", table_name="claim_relationships"
    )
    op.drop_column("claim_relationships", "mutation_evidence")
