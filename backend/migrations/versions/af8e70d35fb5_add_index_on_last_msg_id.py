"""Add index on jobs.last_msg_id for deduplication

Revision ID: af8e70d35fb5
Revises: b91b22e47ed5
Create Date: 2025-10-25 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af8e70d35fb5'
down_revision = 'b91b22e47ed5'  # Your last migration
branch_labels = None
depends_on = None


def upgrade():
    # Create index on last_msg_id for faster duplicate lookups
    op.create_index(
        'idx_jobs_last_msg_id',
        'jobs',
        ['last_msg_id'],
        unique=False
    )


def downgrade():
    # Remove the index
    op.drop_index('idx_jobs_last_msg_id', table_name='jobs')