"""add public profile fields and persistent read timestamps

Revision ID: 8f2c1a6b4d90
Revises: 3d9e71b4c2a6
Create Date: 2026-10-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "8f2c1a6b4d90"
down_revision: Union[str, Sequence[str], None] = "3d9e71b4c2a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    existing = {item["name"] for item in inspect(bind).get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("users", sa.Column("full_name", sa.String(length=80), nullable=True))
    _add_column_if_missing("users", sa.Column("bio", sa.Text(), nullable=True))
    _add_column_if_missing("messages", sa.Column("read_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Keep profile and read timestamp data on downgrade.
    pass
