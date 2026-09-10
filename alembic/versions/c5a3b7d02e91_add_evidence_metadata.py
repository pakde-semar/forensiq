"""add metadata_json to evidence

Revision ID: c5a3b7d02e91
Revises: b2d9f1e04c38
Create Date: 2026-09-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision     = "c5a3b7d02e91"
down_revision = "b2d9f1e04c38"
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column("evidence", sa.Column("metadata_json",         sa.Text,     server_default="{}"))
    op.add_column("evidence", sa.Column("metadata_extracted_at", sa.DateTime, nullable=True))


def downgrade():
    op.drop_column("evidence", "metadata_extracted_at")
    op.drop_column("evidence", "metadata_json")
