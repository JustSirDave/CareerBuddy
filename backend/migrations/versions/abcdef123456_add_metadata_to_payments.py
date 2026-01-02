"""add metadata to payments

Revision ID: abcdef123456
Revises: 731e149ccbaa
Create Date: 2025-12-17
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "abcdef123456"
down_revision: Union[str, None] = "731e149ccbaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if payments table exists before adding column
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'payments' in inspector.get_table_names():
        op.add_column("payments", sa.Column("payment_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Check if payments table exists before dropping column
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if 'payments' in inspector.get_table_names():
        op.drop_column("payments", "payment_metadata")


