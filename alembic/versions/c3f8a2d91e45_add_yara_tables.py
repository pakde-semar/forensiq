"""Add yara_rules and yara_scan_results tables

Revision ID: c3f8a2d91e45
Revises: abd8e1af4676
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f8a2d91e45"
down_revision = "abd8e1af4676"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "yara_rules",
        sa.Column("id",          sa.Integer,     primary_key=True),
        sa.Column("name",        sa.String(255),  nullable=False),
        sa.Column("description", sa.String(500),  server_default=""),
        sa.Column("content",     sa.Text,         nullable=False),
        sa.Column("enabled",     sa.Integer,      server_default="1"),
        sa.Column("source",      sa.String(100),  server_default="custom"),
        sa.Column("tags",        sa.String(255),  server_default=""),
        sa.Column("created_at",  sa.DateTime,     server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime,     server_default=sa.func.now()),
    )
    op.create_table(
        "yara_scan_results",
        sa.Column("id",           sa.Integer,  primary_key=True),
        sa.Column("case_id",      sa.Integer,  sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("scanned_at",   sa.DateTime, server_default=sa.func.now()),
        sa.Column("scanned_by",   sa.String(255), server_default=""),
        sa.Column("file_count",   sa.Integer,  server_default="0"),
        sa.Column("match_count",  sa.Integer,  server_default="0"),
        sa.Column("results_json", sa.Text,     server_default="[]"),
    )


def downgrade():
    op.drop_table("yara_scan_results")
    op.drop_table("yara_rules")
