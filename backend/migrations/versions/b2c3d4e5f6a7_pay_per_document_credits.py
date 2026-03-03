"""pay_per_document_credits

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-28

Replaces subscription tier/quota model with pay-per-document credit system.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Add new credit columns to users ---
    op.add_column("users", sa.Column("free_resume_used", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("free_cover_letter_used", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("document_credits", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("cover_letter_credits", sa.Integer(), nullable=True))

    # --- Set defaults for existing rows ---
    op.execute("UPDATE users SET free_resume_used = false WHERE free_resume_used IS NULL")
    op.execute("UPDATE users SET free_cover_letter_used = false WHERE free_cover_letter_used IS NULL")
    op.execute("UPDATE users SET document_credits = 0 WHERE document_credits IS NULL")
    op.execute("UPDATE users SET cover_letter_credits = 0 WHERE cover_letter_credits IS NULL")

    # --- Grace credits for existing premium users ---
    op.execute(
        "UPDATE users SET document_credits = 2 "
        "WHERE tier = 'pro' AND premium_expires_at > NOW()"
    )

    # --- Make columns NOT NULL now that all rows have values ---
    op.alter_column("users", "free_resume_used", nullable=False, server_default=sa.text("false"))
    op.alter_column("users", "free_cover_letter_used", nullable=False, server_default=sa.text("false"))
    op.alter_column("users", "document_credits", nullable=False, server_default=sa.text("0"))
    op.alter_column("users", "cover_letter_credits", nullable=False, server_default=sa.text("0"))

    # --- Drop old tier/quota columns from users ---
    op.drop_column("users", "tier")
    op.drop_column("users", "generation_count")
    op.drop_column("users", "quota_reset_at")
    op.drop_column("users", "premium_expires_at")

    # --- Create payments table if it doesn't exist ---
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    if "payments" not in inspector.get_table_names():
        op.create_table(
            "payments",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("provider", sa.String(50), server_default="paystack"),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(10), server_default="NGN"),
            sa.Column("status", sa.String(50), server_default="init"),
            sa.Column("reference", sa.String(200), unique=True, index=True),
            sa.Column("product_type", sa.String(20), nullable=True),
            sa.Column("payment_metadata", sa.JSON(), nullable=True),
            sa.Column("raw_webhook", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    else:
        op.add_column("payments", sa.Column("product_type", sa.String(20), nullable=True))


def downgrade() -> None:
    # --- Re-add old columns ---
    op.add_column("users", sa.Column("tier", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("generation_count", sa.String(), nullable=True))
    op.add_column("users", sa.Column("quota_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("premium_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET tier = 'free', generation_count = '{}' WHERE tier IS NULL")
    op.alter_column("users", "tier", nullable=False, server_default=sa.text("'free'"))
    op.alter_column("users", "generation_count", nullable=False, server_default=sa.text("'{}'"))

    # --- Drop new credit columns ---
    op.drop_column("users", "free_resume_used")
    op.drop_column("users", "free_cover_letter_used")
    op.drop_column("users", "document_credits")
    op.drop_column("users", "cover_letter_credits")

    # --- Drop product_type from payments (if table exists) ---
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    if "payments" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("payments")]
        if "product_type" in cols:
            op.drop_column("payments", "product_type")
