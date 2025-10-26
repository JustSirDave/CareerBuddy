"""widen last_msg_id to 255

Revision ID: b91b22e47ed5
Revises: bda51bfbd817
Create Date: 2025-10-25 00:04:52.086043

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b91b22e47ed5'
down_revision: Union[str, None] = 'bda51bfbd817'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Postgres: change VARCHAR(64) -> VARCHAR(255)"""
    op.alter_column(
        "jobs", 
        "last_msg_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True
    )


def downgrade() -> None:
    """Revert to VARCHAR(64)"""
    op.alter_column(
        "jobs",
        "last_msg_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True
    )