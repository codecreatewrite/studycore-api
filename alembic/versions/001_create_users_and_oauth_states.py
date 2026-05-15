"""create users and oauth_states tables

Revision ID: 001
Revises:
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('google_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('picture', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_google_id', 'users', ['google_id'])
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table(
        'oauth_states',
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('state'),
    )


def downgrade() -> None:
    op.drop_table('oauth_states')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_table('users')
