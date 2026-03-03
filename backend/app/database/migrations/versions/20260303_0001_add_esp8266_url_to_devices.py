"""add esp8266_url to devices

Revision ID: 20260303_0001
Revises: f568d8037098
Create Date: 2026-03-03 00:01:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '20260303_0001'
down_revision = 'f568d8037098'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'devices',
        sa.Column('esp8266_url', sa.String(200), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('devices', 'esp8266_url')
