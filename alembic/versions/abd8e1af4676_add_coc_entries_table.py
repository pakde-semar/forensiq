"""add coc_entries table

Revision ID: abd8e1af4676
Revises: 17a5d9780603
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "abd8e1af4676"
down_revision: Union[str, None] = "17a5d9780603"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coc_entries",
        sa.Column("id",          sa.Integer(),     primary_key=True),
        sa.Column("evidence_id", sa.Integer(),     sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("timestamp",   sa.DateTime()),
        sa.Column("action",      sa.String(50),    server_default="received"),
        sa.Column("released_by", sa.String(255),   server_default=""),
        sa.Column("received_by", sa.String(255),   server_default=""),
        sa.Column("purpose",     sa.String(500),   server_default=""),
        sa.Column("location",    sa.String(255),   server_default=""),
        sa.Column("method",      sa.String(100),   server_default=""),
        sa.Column("notes",       sa.Text(),        server_default=""),
    )


def downgrade() -> None:
    op.drop_table("coc_entries")
