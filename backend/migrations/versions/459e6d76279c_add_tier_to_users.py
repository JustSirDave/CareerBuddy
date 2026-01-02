# ============================================================================
# FILE: backend/migrations/script.py.mako
# ============================================================================

"""add_tier_to_users

Revision ID: 459e6d76279c
Revises: e817bbdac60d
Create Date: 2025-11-26 11:15:57.504529

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '459e6d76279c'
down_revision: Union[str, None] = 'e817bbdac60d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tier column to users table
    op.add_column('users', sa.Column('tier', sa.String(length=20), nullable=False, server_default='free'))


def downgrade() -> None:
    # Remove tier column from users table
    op.drop_column('users', 'tier')