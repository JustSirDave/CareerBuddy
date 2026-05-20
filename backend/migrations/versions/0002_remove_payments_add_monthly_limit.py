"""remove payments, add monthly limit

Revision ID: 0002_rm_payments
Revises: 0001_squashed_initial
Create Date: 2026-05-20

- Drop payments table
- Remove credit/payment columns from users
- Add monthly_doc_count and monthly_reset_date to users
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_rm_payments'
down_revision: Union[str, None] = '0001_squashed_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop payments table
    op.drop_index('ix_payments_reference', table_name='payments')
    op.drop_index('ix_payments_job_id', table_name='payments')
    op.drop_index('ix_payments_user_id', table_name='payments')
    op.drop_table('payments')

    # Remove payment/credit columns from users
    op.drop_column('users', 'free_resume_used')
    op.drop_column('users', 'free_cover_letter_used')
    op.drop_column('users', 'document_credits')
    op.drop_column('users', 'cover_letter_credits')
    op.drop_column('users', 'referral_credits')
    op.drop_column('users', 'referred_by_code')

    # Add monthly usage limit columns
    op.add_column('users', sa.Column(
        'monthly_doc_count', sa.Integer(), nullable=False, server_default='0'
    ))
    op.add_column('users', sa.Column(
        'monthly_reset_date', sa.Date(), nullable=True
    ))


def downgrade() -> None:
    op.drop_column('users', 'monthly_reset_date')
    op.drop_column('users', 'monthly_doc_count')

    op.add_column('users', sa.Column('referred_by_code', sa.String(20), nullable=True))
    op.add_column('users', sa.Column('referral_credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('cover_letter_credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('document_credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('free_cover_letter_used', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('free_resume_used', sa.Boolean(), nullable=False, server_default='false'))

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
