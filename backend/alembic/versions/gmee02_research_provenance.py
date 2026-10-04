"""Authenticated evaluation provenance and frozen research splits.

Revision ID: gmee02
Revises: gmee01

Existing votes are conservatively legacy. Duplicate/reversed historical pairs
and their votes are retained; only one representative gets a unique key.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "gmee02"
down_revision = "gmee01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eval_pairs", sa.Column("canonical_key", sa.String(73), nullable=True))
    op.add_column("eval_pairs", sa.Column("split", sa.String(16), server_default="unassigned", nullable=False))
    op.add_column("eval_pairs", sa.Column("event_group", sa.String(128), server_default="unassigned", nullable=False))
    op.add_column("eval_pairs", sa.Column("sampling_provenance", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   LEAST(claim_a_id, claim_b_id)::text || ':' ||
                   GREATEST(claim_a_id, claim_b_id)::text AS pair_key,
                   row_number() OVER (
                       PARTITION BY LEAST(claim_a_id, claim_b_id), GREATEST(claim_a_id, claim_b_id)
                       ORDER BY sampled_at, id
                   ) AS rn
            FROM eval_pairs
        )
        UPDATE eval_pairs p SET canonical_key = r.pair_key
        FROM ranked r WHERE p.id = r.id AND r.rn = 1
    """)
    op.create_unique_constraint("uq_eval_pairs_canonical_key", "eval_pairs", ["canonical_key"])
    op.create_check_constraint("ck_eval_pair_split", "eval_pairs", "split IN ('unassigned', 'train', 'dev', 'test')")
    op.create_index("ix_eval_pairs_split", "eval_pairs", ["split"])
    op.create_index("ix_eval_pairs_event_group", "eval_pairs", ["event_group"])

    op.add_column("eval_pair_labels", sa.Column("origin", sa.String(16), server_default="legacy", nullable=False))
    op.add_column("eval_pair_labels", sa.Column("annotator_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("eval_pair_labels", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("eval_pair_labels", sa.Column("mutation_types", postgresql.JSONB(), nullable=True))
    op.add_column("eval_pair_labels", sa.Column("notes", sa.String(2000), nullable=True))
    op.add_column("eval_pair_labels", sa.Column("provenance", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("eval_pair_labels", sa.Column("history", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.create_foreign_key("fk_eval_label_user", "eval_pair_labels", "users", ["annotator_user_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_eval_label_origin", "eval_pair_labels", "origin IN ('human', 'automatic', 'legacy', 'test')")
    op.drop_constraint("uq_eval_label_pair_annotator", "eval_pair_labels", type_="unique")
    op.create_unique_constraint("uq_eval_label_pair_annotator_origin", "eval_pair_labels", ["pair_id", "annotator", "origin"])
    op.create_index("ix_eval_pair_labels_origin", "eval_pair_labels", ["origin"])
    op.create_index("ix_eval_pair_labels_annotator_user_id", "eval_pair_labels", ["annotator_user_id"])


def downgrade() -> None:
    # Never solve a downgrade conflict by deleting votes or throwing away revisions.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM eval_pair_labels
                WHERE origin <> 'legacy' OR annotator_user_id IS NOT NULL
                   OR history <> '[]'::jsonb OR mutation_types IS NOT NULL
                   OR notes IS NOT NULL OR provenance <> '{}'::jsonb
            ) OR EXISTS (
                SELECT 1 FROM eval_pairs
                WHERE split <> 'unassigned' OR event_group <> 'unassigned'
                   OR sampling_provenance <> '{}'::jsonb
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade gmee02 without losing research provenance; retain gmee02 or restore a pre-research backup';
            END IF;
        END $$
    """)
    op.drop_index("ix_eval_pair_labels_annotator_user_id", table_name="eval_pair_labels")
    op.drop_index("ix_eval_pair_labels_origin", table_name="eval_pair_labels")
    op.drop_constraint("uq_eval_label_pair_annotator_origin", "eval_pair_labels", type_="unique")
    op.create_unique_constraint("uq_eval_label_pair_annotator", "eval_pair_labels", ["pair_id", "annotator"])
    op.drop_constraint("ck_eval_label_origin", "eval_pair_labels", type_="check")
    op.drop_constraint("fk_eval_label_user", "eval_pair_labels", type_="foreignkey")
    for name in ("history", "provenance", "notes", "mutation_types", "updated_at", "annotator_user_id", "origin"):
        op.drop_column("eval_pair_labels", name)
    op.drop_index("ix_eval_pairs_event_group", table_name="eval_pairs")
    op.drop_index("ix_eval_pairs_split", table_name="eval_pairs")
    op.drop_constraint("ck_eval_pair_split", "eval_pairs", type_="check")
    op.drop_constraint("uq_eval_pairs_canonical_key", "eval_pairs", type_="unique")
    for name in ("sampling_provenance", "event_group", "split", "canonical_key"):
        op.drop_column("eval_pairs", name)
