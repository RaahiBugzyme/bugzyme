"""add user phone_number, email_verified, push_token, deactivation columns and blocks/reports/email_verification_tokens tables

Revision ID: add_mvp_user_columns_and_tables
Revises: 7c2f4a91d6b3
Create Date: 2026-11-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "add_mvp_user_columns_and_tables"
down_revision: Union[str, Sequence[str], None] = "7c2f4a91d6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # --- Add columns to users table if missing ---
    if inspector.has_table("users"):
        user_columns = {c["name"] for c in inspector.get_columns("users")}

        if "phone_number" not in user_columns:
            op.add_column(
                "users",
                sa.Column("phone_number", sa.String(length=20), nullable=True, unique=True, index=True),
            )
        if "email_verified" not in user_columns:
            op.add_column(
                "users",
                sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "push_token" not in user_columns:
            op.add_column(
                "users",
                sa.Column("push_token", sa.String(length=500), nullable=True),
            )
        if "is_deactivated" not in user_columns:
            op.add_column(
                "users",
                sa.Column("is_deactivated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "deactivated_at" not in user_columns:
            op.add_column(
                "users",
                sa.Column("deactivated_at", sa.DateTime(), nullable=True),
            )

    # --- Create blocks table ---
    if not inspector.has_table("blocks"):
        op.create_table(
            "blocks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "blocker_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "blocked_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocks_blocker_blocked"),
        )
        op.create_index("ix_blocks_blocker_blocked", "blocks", ["blocker_id", "blocked_id"], unique=True)

    # --- Create reports table ---
    if not inspector.has_table("reports"):
        op.create_table(
            "reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "reporter_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "reported_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "reported_message_id",
                sa.Integer(),
                sa.ForeignKey("messages.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("reason", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column(
                "reviewed_by",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # --- Create email_verification_tokens table ---
    if not inspector.has_table("email_verification_tokens"):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token", sa.String(length=128), unique=True, index=True, nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("email_verification_tokens"):
        op.drop_table("email_verification_tokens")
    if inspector.has_table("reports"):
        op.drop_table("reports")
    if inspector.has_table("blocks"):
        op.drop_table("blocks")

    if inspector.has_table("users"):
        user_columns = {c["name"] for c in inspector.get_columns("users")}
        if "deactivated_at" in user_columns:
            op.drop_column("users", "deactivated_at")
        if "is_deactivated" in user_columns:
            op.drop_column("users", "is_deactivated")
        if "push_token" in user_columns:
            op.drop_column("users", "push_token")
        if "email_verified" in user_columns:
            op.drop_column("users", "email_verified")
        if "phone_number" in user_columns:
            op.drop_column("users", "phone_number")
