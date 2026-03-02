"""add onboarding fields to users

Revision ID: f1a2b3c4d5e6
Revises: 8aa3779ba631
Create Date: 2026-03-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "8aa3779ba631"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("onboarding_step", sa.String(50), nullable=True))
    op.execute("UPDATE users SET onboarding_complete = true")


def downgrade() -> None:
    op.drop_column("users", "onboarding_step")
    op.drop_column("users", "onboarding_complete")
