"""add private opt-in AI memory settings

Revision ID: a41d9e7c2b60
Revises: 8f2c1a6b4d90
Create Date: 2026-10-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "a41d9e7c2b60"
down_revision: Union[str, Sequence[str], None] = "8f2c1a6b4d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(column: sa.Column) -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("users")}
    if column.name not in columns:
        op.add_column("users", column)


def upgrade() -> None:
    _add_column_if_missing(sa.Column(
        "ai_memory_enabled", sa.Boolean(), nullable=False,
        server_default=sa.false(),
    ))
    _add_column_if_missing(sa.Column(
        "ai_memory_processed_through_message_id", sa.Integer(), nullable=True,
    ))


def downgrade() -> None:
    # Keep user privacy settings and processing cursor on downgrade.
    pass
