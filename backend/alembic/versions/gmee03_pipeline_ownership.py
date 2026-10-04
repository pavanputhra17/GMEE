"""Durable pipeline ownership and job records.

Revision ID: gmee03
Revises: gmee02

Additive only. Existing rows keep their statuses; legacy rows stranded in a
``processing`` state before this revision have NULL leases and are NOT
auto-recovered — an admin must opt in via ``POST /api/v1/operations/recover``
with ``include_unleased=true`` after confirming no worker is running.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "gmee03"
down_revision = "gmee02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("claimed_by", sa.String(64), nullable=True))
    op.add_column("articles", sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "articles",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("articles", sa.Column("last_error", sa.String(500), nullable=True))
    # Queue scans: "ready for stage" and "expired claims for recovery".
    op.create_index("ix_articles_processing_status", "articles", ["processing_status"])
    op.create_index("ix_articles_nlp_queue", "articles", ["processing_status", "nlp_status"])
    op.create_index("ix_articles_claim_expires_at", "articles", ["claim_expires_at"])

    op.create_table(
        "pipeline_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'abandoned')",
            name="ck_pipeline_jobs_status",
        ),
    )
    op.create_index(
        "uq_pipeline_jobs_one_running",
        "pipeline_jobs",
        ["job_type"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_index("ix_pipeline_jobs_type_started", "pipeline_jobs", ["job_type", "started_at"])


def downgrade() -> None:
    # Drops operational metadata only; article content/statuses are untouched.
    op.drop_index("ix_pipeline_jobs_type_started", table_name="pipeline_jobs")
    op.drop_index("uq_pipeline_jobs_one_running", table_name="pipeline_jobs")
    op.drop_table("pipeline_jobs")
    op.drop_index("ix_articles_claim_expires_at", table_name="articles")
    op.drop_index("ix_articles_nlp_queue", table_name="articles")
    op.drop_index("ix_articles_processing_status", table_name="articles")
    op.drop_column("articles", "last_error")
    op.drop_column("articles", "attempt_count")
    op.drop_column("articles", "claim_expires_at")
    op.drop_column("articles", "claimed_by")
