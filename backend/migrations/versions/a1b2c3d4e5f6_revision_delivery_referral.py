"""revision_delivery_referral

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-01-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Job: revision + delivery confirmation
    op.add_column("jobs", sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("revision_answers", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("delivery_confirmation_sent", sa.Boolean(), nullable=False, server_default="false"))

    # User: telegram_first_name + referral
    op.add_column("users", sa.Column("telegram_first_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("referral_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("referred_by_code", sa.String(20), nullable=True))

    # Referrals table
    op.create_table(
        "referrals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("referrer_id", sa.String(), nullable=False),
        sa.Column("referee_id", sa.String(), nullable=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=True, server_default="pending"),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referee_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_referrals_code"), "referrals", ["code"], unique=True)
    op.create_index(op.f("ix_referrals_referrer_id"), "referrals", ["referrer_id"], unique=False)
    op.create_index(op.f("ix_referrals_referee_id"), "referrals", ["referee_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_referrals_referee_id"), table_name="referrals")
    op.drop_index(op.f("ix_referrals_referrer_id"), table_name="referrals")
    op.drop_index(op.f("ix_referrals_code"), table_name="referrals")
    op.drop_table("referrals")
    op.drop_column("users", "referred_by_code")
    op.drop_column("users", "referral_credits")
    op.drop_column("users", "telegram_first_name")
    op.drop_column("jobs", "delivery_confirmation_sent")
    op.drop_column("jobs", "completed_at")
    op.drop_column("jobs", "revision_answers")
    op.drop_column("jobs", "revision_count")
