"""add message attachment metadata

Revision ID: 6a4f2b8c91de
Revises: 1d5280e25742
Create Date: 2026-09-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "6a4f2b8c91de"
down_revision: Union[str, Sequence[str], None] = "1d5280e25742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(column: sa.Column) -> None:
    context = op.get_context()
    if context.as_sql:
        if context.dialect.name != "postgresql":
            raise RuntimeError(
                "Offline idempotent attachment migration requires PostgreSQL"
            )
        op.add_column("messages", column, if_not_exists=True)
        return

    bind = op.get_bind()
    columns = {
        item["name"]: item
        for item in inspect(bind).get_columns("messages")
    }
    if column.name not in columns:
        op.add_column(
            "messages",
            column,
            if_not_exists=bind.dialect.name == "postgresql",
        )
        columns = {
            item["name"]: item
            for item in inspect(bind).get_columns("messages")
        }

    actual = columns.get(column.name)
    if actual is None:
        raise RuntimeError(f"messages.{column.name} was not created")
    expected_type = column.type.compile(dialect=bind.dialect).upper()
    actual_type = actual["type"].compile(dialect=bind.dialect).upper()
    if actual_type != expected_type or actual["nullable"] is not True:
        raise RuntimeError(
            f"messages.{column.name} exists with incompatible definition: "
            f"type={actual_type}, nullable={actual['nullable']}"
        )


def upgrade() -> None:
    _add_column_if_missing(
        sa.Column("attachment_storage_key", sa.String(length=64), nullable=True)
    )
    _add_column_if_missing(
        sa.Column("attachment_name", sa.String(length=255), nullable=True)
    )
    _add_column_if_missing(
        sa.Column("attachment_mime_type", sa.String(length=100), nullable=True)
    )
    _add_column_if_missing(
        sa.Column("attachment_size_bytes", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    # Keep additive metadata columns on downgrade. They may have been created
    # by startup repair or predate this revision; dropping them can destroy
    # data that this migration did not create.
    pass
