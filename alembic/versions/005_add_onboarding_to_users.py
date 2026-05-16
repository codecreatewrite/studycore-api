"""add onboarding_completed to users

Revision ID: 005
Revises: 004
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'onboarding_completed',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        )
    )


def downgrade() -> None:
    op.drop_column('users', 'onboarding_completed')
