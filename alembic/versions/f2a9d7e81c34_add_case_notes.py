"""Add case_notes table

Revision ID: f2a9d7e81c34
Revises: e8f1c3a02b67
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "f2a9d7e81c34"
down_revision = "e8f1c3a02b67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "case_notes",
        sa.Column("id",         sa.Integer, primary_key=True),
        sa.Column("case_id",    sa.Integer, sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("title",      sa.String(255), server_default="Untitled", nullable=False),
        sa.Column("content",    sa.Text,    server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("case_notes")
