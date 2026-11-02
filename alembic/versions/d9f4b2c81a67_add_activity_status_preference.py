"""persist user activity status visibility preference

Revision ID: d9f4b2c81a67
Revises: ba28df14c601
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "d9f4b2c81a67"
down_revision: Union[str, Sequence[str], None] = "ba28df14c601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "activity_status_enabled" not in columns:
        op.add_column(
            "users",
            sa.Column("activity_status_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "activity_status_enabled" in columns:
        op.drop_column("users", "activity_status_enabled")
