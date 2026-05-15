"""create recall_attempts table

Revision ID: 003
Revises: 002
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recall_attempts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('concept_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('fsrs_rating', sa.Integer(), nullable=True),
        sa.Column('ai_coverage_score', sa.Float(), nullable=True),
        sa.Column('ai_depth_score', sa.Float(), nullable=True),
        sa.Column('ai_gap_map', sa.JSON(), nullable=True),
        sa.Column('ai_tip', sa.Text(), nullable=True),
        sa.Column('ai_eval_question', sa.Text(), nullable=True),
        sa.Column('ai_eval_answer', sa.Text(), nullable=True),
        sa.Column('ai_eval_feedback', sa.Text(), nullable=True),
        sa.Column('fsrs_stability_after', sa.Float(), nullable=True),
        sa.Column('fsrs_difficulty_after', sa.Float(), nullable=True),
        sa.Column('scheduled_days', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['concept_id'], ['concepts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_recall_attempts_concept_id', 'recall_attempts', ['concept_id'])
    op.create_index('ix_recall_attempts_user_id', 'recall_attempts', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_recall_attempts_user_id', table_name='recall_attempts')
    op.drop_index('ix_recall_attempts_concept_id', table_name='recall_attempts')
    op.drop_table('recall_attempts')
