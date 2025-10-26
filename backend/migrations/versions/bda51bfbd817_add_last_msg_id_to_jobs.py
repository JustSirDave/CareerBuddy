"""add last_msg_id to jobs

Revision ID: bda51bfbd817
Revises: 38d07a7bdfe3
Create Date: 2025-10-24 23:17:45.827916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bda51bfbd817'
down_revision: Union[str, Sequence[str], None] = '38d07a7bdfe3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "jobs",
        sa.Column("last_msg_id", sa.String(length=64), nullable=True)
    )

def downgrade():
    # Remove the index
    op.drop_index('idx_jobs_last_msg_id', table_name='jobs')