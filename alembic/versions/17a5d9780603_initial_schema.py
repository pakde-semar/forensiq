"""initial schema

Revision ID: 17a5d9780603
Revises:
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "17a5d9780603"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agency",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("unit", sa.String(255), server_default=""),
        sa.Column("address", sa.String(500), server_default=""),
        sa.Column("city", sa.String(100), server_default=""),
        sa.Column("country", sa.String(100), server_default=""),
        sa.Column("phone", sa.String(50), server_default=""),
        sa.Column("email", sa.String(255), server_default=""),
        sa.Column("website", sa.String(255), server_default=""),
        sa.Column("logo_path", sa.String(500), server_default=""),
        sa.Column("case_prefix", sa.String(20), server_default="CASE"),
        sa.Column("supervisor_name", sa.String(255), server_default=""),
        sa.Column("supervisor_title", sa.String(255), server_default=""),
        sa.Column("evidence_intake_email", sa.String(255), server_default=""),
        sa.Column("legal_records_custodian", sa.String(255), server_default=""),
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_number", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("case_type", sa.String(100), server_default=""),
        sa.Column("status", sa.String(50), server_default="Open"),
        sa.Column("priority", sa.String(50), server_default="Medium"),
        sa.Column("classification", sa.String(100), server_default="Confidential"),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("misp_event_id", sa.String(100), server_default=""),
        sa.Column("flowintel_case_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "investigators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), server_default=""),
        sa.Column("timeclock_minutes", sa.Integer(), server_default="0"),
        sa.Column("is_lead", sa.Integer(), server_default="0"),
        sa.Column("added_at", sa.DateTime()),
    )

    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("evidence_number", sa.String(50), nullable=False),
        sa.Column("coc_number", sa.String(50), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), server_default=""),
        sa.Column("file_size", sa.BigInteger(), server_default="0"),
        sa.Column("category", sa.String(100), server_default="Other"),
        sa.Column("original_location", sa.String(1000), server_default=""),
        sa.Column("submitter", sa.String(255), server_default=""),
        sa.Column("md5", sa.String(32), server_default=""),
        sa.Column("sha256", sa.String(64), server_default=""),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("date_added", sa.DateTime()),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime()),
        sa.Column("app_name", sa.String(100), server_default="ForensiQ"),
        sa.Column("investigator", sa.String(255), server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("format", sa.String(10), server_default="html"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("created_by", sa.String(255), server_default=""),
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("pipeline_label", sa.String(200), server_default=""),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("input_type", sa.String(50), server_default="case"),
        sa.Column("input_ref", sa.String(500), server_default=""),
        sa.Column("steps_json", sa.Text(), server_default="[]"),
        sa.Column("triggered_by", sa.String(100), server_default="auto"),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pipeline_runs")
    op.drop_table("reports")
    op.drop_table("audit_logs")
    op.drop_table("evidence")
    op.drop_table("investigators")
    op.drop_table("cases")
    op.drop_table("agency")
