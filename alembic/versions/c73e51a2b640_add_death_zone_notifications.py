"""persist per-user death-zone suggestions and notification lifecycle

Revision ID: c73e51a2b640
Revises: a41d9e7c2b60
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "c73e51a2b640"
down_revision: Union[str, Sequence[str], None] = "a41d9e7c2b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "death_zone_conversation_states" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "death_zone_conversation_states",
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("last_message_id", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if "death_zone_notifications" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "death_zone_notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_key", sa.String(length=100), nullable=False),
            sa.Column("trigger_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="generating"),
            sa.Column("suggestions_json", sa.Text(), nullable=True),
            sa.Column("death_zone_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("viewed_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("chat_id", "user_id", "event_key", name="uq_death_zone_user_event"),
        )
    indexes = {item["name"] for item in inspect(op.get_bind()).get_indexes("death_zone_notifications")}
    if "ix_death_zone_user_state" not in indexes:
        op.create_index("ix_death_zone_user_state", "death_zone_notifications", ["user_id", "status", "expires_at"])
    if "ix_death_zone_chat_event" not in indexes:
        op.create_index("ix_death_zone_chat_event", "death_zone_notifications", ["chat_id", "event_key"])


def downgrade() -> None:
    # Preserve user notification history if a deployment is rolled back.
    pass
