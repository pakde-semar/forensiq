"""add notifications and alert_rules

Revision ID: d6f4a2e95b07
Revises: c5a3b7d02e91
Create Date: 2026-09-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd6f4a2e95b07'
down_revision = 'c5a3b7d02e91'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id',         sa.Integer(), primary_key=True),
        sa.Column('case_id',    sa.Integer(), sa.ForeignKey('cases.id'), nullable=True),
        sa.Column('rule_type',  sa.String(50), nullable=False),
        sa.Column('severity',   sa.String(20), default='info'),
        sa.Column('title',      sa.String(255), nullable=False),
        sa.Column('body',       sa.Text(), default=''),
        sa.Column('link',       sa.String(500), default=''),
        sa.Column('is_read',    sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'alert_rules',
        sa.Column('id',          sa.Integer(), primary_key=True),
        sa.Column('name',        sa.String(255), nullable=False),
        sa.Column('rule_type',   sa.String(50), nullable=False, unique=True),
        sa.Column('enabled',     sa.Integer(), default=1),
        sa.Column('config_json', sa.Text(), default='{}'),
        sa.Column('created_at',  sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('notifications')
    op.drop_table('alert_rules')
