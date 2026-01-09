# ============================================================================
# FILE: backend/migrations/script.py.mako
# ============================================================================

"""migrate_to_telegram

Revision ID: 8aa3779ba631
Revises: abcdef123456
Create Date: 2026-01-07 10:17:57.290738

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8aa3779ba631'
down_revision: Union[str, None] = 'abcdef123456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate from WhatsApp (wa_id) to Telegram (telegram_user_id)"""
    
    # Check if users table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    if "users" not in inspector.get_table_names():
        print("[MIGRATION] 'users' table does not exist, skipping migration.")
        return
    
    # Add new Telegram columns
    op.add_column('users', sa.Column('telegram_user_id', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('telegram_username', sa.String(length=100), nullable=True))
    
    # Copy wa_id to telegram_user_id for existing users
    op.execute("UPDATE users SET telegram_user_id = wa_id WHERE telegram_user_id IS NULL")
    
    # Now make telegram_user_id non-nullable
    op.alter_column('users', 'telegram_user_id', nullable=False)
    
    # Create index and unique constraint
    op.create_index('ix_users_telegram_user_id', 'users', ['telegram_user_id'], unique=False)
    op.create_unique_constraint('uq_users_telegram_user_id', 'users', ['telegram_user_id'])
        # Drop old wa_id constraint and column
    op.drop_constraint('users_wa_id_key', 'users', type_='unique')
    op.drop_column('users', 'wa_id')


def downgrade() -> None:
    """Rollback: Migrate from Telegram back to WhatsApp"""
    
    # Add back wa_id column
    op.add_column('users', sa.Column('wa_id', sa.String(length=50), nullable=True))
    
    # Copy telegram_user_id to wa_id
    op.execute("UPDATE users SET wa_id = telegram_user_id WHERE wa_id IS NULL")
    
    # Make wa_id non-nullable
    op.alter_column('users', 'wa_id', nullable=False)
    
    # Recreate unique constraint for wa_id
    op.create_unique_constraint('users_wa_id_key', 'users', ['wa_id'])
    
    # Drop Telegram columns
    op.drop_constraint('uq_users_telegram_user_id', 'users', type_='unique')
    op.drop_index('ix_users_telegram_user_id', table_name='users')
    op.drop_column('users', 'telegram_username')
    op.drop_column('users', 'telegram_user_id')