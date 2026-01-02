# ============================================================================
# FILE: backend/migrations/script.py.mako
# ============================================================================

"""add_generation_count_to_users

Revision ID: 731e149ccbaa
Revises: 459e6d76279c
Create Date: 2025-11-26 15:07:17.615780

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '731e149ccbaa'
down_revision: Union[str, None] = '459e6d76279c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add generation_count column to users table
    op.add_column('users', sa.Column('generation_count', sa.String(), nullable=False, server_default='{}'))


def downgrade() -> None:
    # Remove generation_count column from users table
    op.drop_column('users', 'generation_count')