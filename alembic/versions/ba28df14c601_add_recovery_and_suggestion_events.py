"""add private recovery and suggestion lifecycle records

Revision ID: ba28df14c601
Revises: c73e51a2b640
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "ba28df14c601"
down_revision: Union[str, Sequence[str], None] = "c73e51a2b640"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    names = set(inspect(op.get_bind()).get_table_names())
    if "ai_recovery_interventions" not in names:
        op.create_table(
            "ai_recovery_interventions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("trigger_message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("recovery_reason", sa.String(80), nullable=False),
            sa.Column("strategy", sa.String(60), nullable=False),
            sa.Column("prompt_version", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
            sa.Column("outcome_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("evaluated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("chat_id", "user_id", "trigger_message_id", name="uq_ai_recovery_trigger"),
        )
        op.create_index("ix_ai_recovery_chat_user", "ai_recovery_interventions", ["chat_id", "user_id", "created_at"])
    if "ai_suggestion_records" not in names:
        op.create_table(
            "ai_suggestion_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("intervention_id", sa.Integer(), sa.ForeignKey("ai_recovery_interventions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("suggestion_hash", sa.String(64), nullable=False),
            sa.Column("strategy", sa.String(60), nullable=False),
            sa.Column("prompt_version", sa.String(40), nullable=False),
            sa.Column("model_id", sa.String(100), nullable=False),
            sa.Column("validation_passed", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ai_suggestion_chat_user", "ai_suggestion_records", ["chat_id", "user_id", "created_at"])
    if "ai_suggestion_events" not in names:
        op.create_table(
            "ai_suggestion_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("suggestion_id", sa.Integer(), sa.ForeignKey("ai_suggestion_records.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("event_key", sa.String(100), nullable=False),
            sa.Column("event_type", sa.String(32), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("suggestion_id", "event_key", name="uq_ai_suggestion_event_key"),
        )
        op.create_index("ix_ai_suggestion_event_chat_user", "ai_suggestion_events", ["chat_id", "user_id", "event_type"])

def downgrade() -> None:
    op.drop_table("ai_suggestion_events")
    op.drop_table("ai_suggestion_records")
    op.drop_table("ai_recovery_interventions")
