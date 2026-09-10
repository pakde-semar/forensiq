"""add case_tags table

Revision ID: b2d9f1e04c38
Revises: a1c4f8e03b29
Create Date: 2026-09-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision     = "b2d9f1e04c38"
down_revision = "a1c4f8e03b29"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "case_tags",
        sa.Column("id",      sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("name",    sa.String(50), nullable=False),
        sa.Column("color",   sa.String(7),  server_default="#89b4fa"),
    )


def downgrade():
    op.drop_table("case_tags")
