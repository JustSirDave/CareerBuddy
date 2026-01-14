"""
Add premium tracking fields to users table
Migration created: 2026-01-14
Author: Sir Dave
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add quota_reset_at and premium_expires_at columns to users table"""
    op.add_column('users', sa.Column('quota_reset_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('premium_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    """Remove quota_reset_at and premium_expires_at columns from users table"""
    op.drop_column('users', 'premium_expires_at')
    op.drop_column('users', 'quota_reset_at')
