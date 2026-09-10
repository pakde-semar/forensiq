"""add enrichment tables

Revision ID: a1c4f8e03b29
Revises: f2a9d7e81c34
Create Date: 2026-09-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision     = "a1c4f8e03b29"
down_revision = "f2a9d7e81c34"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "app_settings",
        sa.Column("key",   sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False, server_default=""),
    )
    op.create_table(
        "enrichment_results",
        sa.Column("id",          sa.Integer, primary_key=True),
        sa.Column("case_id",     sa.Integer, sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("ioc_type",    sa.String(50),  nullable=False),
        sa.Column("ioc_value",   sa.String(500), nullable=False),
        sa.Column("provider",    sa.String(50),  nullable=False),
        sa.Column("queried_at",  sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("queried_by",  sa.String(255), server_default=""),
        sa.Column("verdict",     sa.String(20),  server_default="unknown"),
        sa.Column("summary",     sa.String(500), server_default=""),
        sa.Column("result_json", sa.Text,        server_default="{}"),
    )


def downgrade():
    op.drop_table("enrichment_results")
    op.drop_table("app_settings")
