"""create courses, concepts, and key_points tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'courses',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('exam_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_courses_user_id', 'courses', ['user_id'])

    op.create_table(
        'concepts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('course_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('lifecycle', sa.String(), nullable=False, server_default='draft'),
        sa.Column('fsrs_stability', sa.Float(), nullable=True),
        sa.Column('fsrs_difficulty', sa.Float(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recall_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_ai_score', sa.Float(), nullable=True),
        sa.Column('avg_ai_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_recalled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_concepts_user_id', 'concepts', ['user_id'])
    op.create_index('ix_concepts_course_id', 'concepts', ['course_id'])

    op.create_table(
        'key_points',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('concept_id', sa.String(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_critical', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['concept_id'], ['concepts.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_key_points_concept_id', 'key_points', ['concept_id'])


def downgrade() -> None:
    op.drop_index('ix_key_points_concept_id', table_name='key_points')
    op.drop_table('key_points')
    op.drop_index('ix_concepts_course_id', table_name='concepts')
    op.drop_index('ix_concepts_user_id', table_name='concepts')
    op.drop_table('concepts')
    op.drop_index('ix_courses_user_id', table_name='courses')
    op.drop_table('courses')
