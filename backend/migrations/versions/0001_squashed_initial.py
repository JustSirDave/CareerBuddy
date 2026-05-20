"""squashed initial schema

Revision ID: 0001_squashed_initial
Revises:
Create Date: 2026-05-20

Single clean migration replacing the broken historical chain.
Matches the current SQLAlchemy models exactly.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_squashed_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('telegram_user_id', sa.String(50), nullable=False),
        sa.Column('telegram_username', sa.String(100), nullable=True),
        sa.Column('telegram_first_name', sa.String(100), nullable=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('locale', sa.String(10), nullable=True),
        sa.Column('free_resume_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('free_cover_letter_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('document_credits', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('cover_letter_credits', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('onboarding_complete', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('onboarding_step', sa.String(50), nullable=True),
        sa.Column('referral_credits', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('referred_by_code', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_telegram_user_id', 'users', ['telegram_user_id'], unique=True)

    # --- jobs ---
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=True, server_default=sa.text("'collecting'")),
        sa.Column('answers', sa.JSON(), nullable=True),
        sa.Column('draft_text', sa.String(), nullable=True),
        sa.Column('final_text', sa.String(), nullable=True),
        sa.Column('last_msg_id', sa.String(255), nullable=True),
        sa.Column('revision_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('revision_answers', sa.JSON(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivery_confirmation_sent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_user_id', 'jobs', ['user_id'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_index('ix_jobs_last_msg_id', 'jobs', ['last_msg_id'])

    # --- messages ---
    op.create_table(
        'messages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=True),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_user_id', 'messages', ['user_id'])
    op.create_index('ix_messages_job_id', 'messages', ['job_id'])

    # --- payments ---
    op.create_table(
        'payments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=True),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('reference', sa.String(200), nullable=True),
        sa.Column('product_type', sa.String(20), nullable=True),
        sa.Column('payment_metadata', sa.JSON(), nullable=True),
        sa.Column('raw_webhook', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_job_id', 'payments', ['job_id'])
    op.create_index('ix_payments_reference', 'payments', ['reference'], unique=True)

    # --- referrals ---
    op.create_table(
        'referrals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('referrer_id', sa.String(), nullable=False),
        sa.Column('referee_id', sa.String(), nullable=True),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['referrer_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['referee_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_referrals_referrer_id', 'referrals', ['referrer_id'])
    op.create_index('ix_referrals_referee_id', 'referrals', ['referee_id'])
    op.create_index('ix_referrals_code', 'referrals', ['code'], unique=True)


def downgrade() -> None:
    op.drop_table('referrals')
    op.drop_table('payments')
    op.drop_table('messages')
    op.drop_table('jobs')
    op.drop_table('users')
