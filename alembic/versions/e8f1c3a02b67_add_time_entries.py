"""Add time_entries table

Revision ID: e8f1c3a02b67
Revises: d5e7b4c09f12
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "e8f1c3a02b67"
down_revision = "d5e7b4c09f12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "time_entries",
        sa.Column("id",               sa.Integer, primary_key=True),
        sa.Column("investigator_id",  sa.Integer, sa.ForeignKey("investigators.id"), nullable=False),
        sa.Column("case_id",          sa.Integer, sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("clock_in",         sa.DateTime, nullable=False),
        sa.Column("clock_out",        sa.DateTime, nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("activity",         sa.String(500), server_default=""),
        sa.Column("entry_type",       sa.String(20),  server_default="clockinout"),
    )


def downgrade():
    op.drop_table("time_entries")
