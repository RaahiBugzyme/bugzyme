"""add monotonic revision to message reaction state

Revision ID: 3d9e71b4c2a6
Revises: 7c2f4a91d6b3
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "3d9e71b4c2a6"
down_revision: Union[str, Sequence[str], None] = "7c2f4a91d6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    column = sa.Column(
        "reaction_revision",
        sa.Integer(),
        server_default=sa.text("0"),
        nullable=False,
    )
    context = op.get_context()
    if context.as_sql:
        if context.dialect.name != "postgresql":
            raise RuntimeError(
                "Offline idempotent reaction revision migration requires PostgreSQL"
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
        raise RuntimeError("messages.reaction_revision was not created")
    actual_type = actual["type"].compile(dialect=bind.dialect).upper()
    if actual_type != "INTEGER" or actual["nullable"] is not False:
        raise RuntimeError(
            "messages.reaction_revision exists with incompatible definition: "
            f"type={actual_type}, nullable={actual['nullable']}"
        )


def downgrade() -> None:
    # Preserve the counter if it predated this revision; its values are
    # harmless to earlier code and safe to retain across a downgrade.
    pass
