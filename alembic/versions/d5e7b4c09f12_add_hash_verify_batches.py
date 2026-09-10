"""Add hash_verify_batches table

Revision ID: d5e7b4c09f12
Revises: c3f8a2d91e45
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e7b4c09f12"
down_revision = "c3f8a2d91e45"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hash_verify_batches",
        sa.Column("id",             sa.Integer,  primary_key=True),
        sa.Column("case_id",        sa.Integer,  sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("run_at",         sa.DateTime, server_default=sa.func.now()),
        sa.Column("run_by",         sa.String(255), server_default=""),
        sa.Column("total",          sa.Integer,  server_default="0"),
        sa.Column("ok_count",       sa.Integer,  server_default="0"),
        sa.Column("tampered_count", sa.Integer,  server_default="0"),
        sa.Column("missing_count",  sa.Integer,  server_default="0"),
        sa.Column("no_hash_count",  sa.Integer,  server_default="0"),
        sa.Column("results_json",   sa.Text,     server_default="[]"),
    )


def downgrade():
    op.drop_table("hash_verify_batches")
