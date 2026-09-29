"""dedupe claim_relationships and enforce one edge per (from, to, type)

Revision ID: a4c7e1f9b2d6
Revises: f7d3e9b2c5a6
Create Date: 2026-09-25
"""

from alembic import op

revision = "a4c7e1f9b2d6"
down_revision = "f7d3e9b2c5a6"
branch_labels = None
depends_on = None

# Repeated evolution cycles used to append one copy of every edge per run.
# Keep the highest-scoring copy (ties: oldest, then lowest id) so the unique
# constraint can be created on a live database that already has duplicates.
_DEDUPE = """
DELETE FROM claim_relationships
WHERE id IN (
    SELECT id
    FROM (
        SELECT id,
               row_number() OVER (
                   PARTITION BY from_claim_id, to_claim_id, relationship_type
                   ORDER BY score DESC, created_at ASC, id ASC
               ) AS rn
        FROM claim_relationships
    ) ranked
    WHERE ranked.rn > 1
)
"""


def upgrade() -> None:
    op.execute(_DEDUPE)
    op.create_unique_constraint(
        "uq_claim_relationships_edge",
        "claim_relationships",
        ["from_claim_id", "to_claim_id", "relationship_type"],
    )


def down() -> None:
    op.drop_constraint(
        "uq_claim_relationships_edge", "claim_relationships", type_="unique"
    )
