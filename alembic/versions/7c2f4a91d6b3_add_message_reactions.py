"""add persistent message reactions

Revision ID: 7c2f4a91d6b3
Revises: 6a4f2b8c91de
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "7c2f4a91d6b3"
down_revision: Union[str, Sequence[str], None] = "6a4f2b8c91de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _reaction_table_definition():
    return (
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reaction", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "message_id",
            "user_id",
            name="uq_message_reaction_user",
        ),
        sa.CheckConstraint(
            "reaction IN ('❤️', '😂', '👍', '🔥', '😮', '😢')",
            name="ck_message_reaction_allowed",
        ),
    )


def _validate_existing_table(bind) -> None:
    inspector = inspect(bind)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("message_reactions")
    }
    required = {
        "id": sa.Integer(),
        "message_id": sa.Integer(),
        "user_id": sa.Integer(),
        "reaction": sa.String(length=16),
        "created_at": sa.DateTime(),
    }
    for name, expected_type in required.items():
        actual = columns.get(name)
        if actual is None:
            raise RuntimeError(f"message_reactions.{name} is missing")
        expected_type_name = expected_type.compile(dialect=bind.dialect).upper()
        actual_type = actual["type"].compile(dialect=bind.dialect).upper()
        if actual_type != expected_type_name or actual["nullable"] is not False:
            raise RuntimeError(
                f"message_reactions.{name} has incompatible definition: "
                f"type={actual_type}, nullable={actual['nullable']}"
            )

    unique_constraints = inspector.get_unique_constraints("message_reactions")
    if not any(
        constraint.get("name") == "uq_message_reaction_user"
        and constraint.get("column_names") == ["message_id", "user_id"]
        for constraint in unique_constraints
    ):
        raise RuntimeError(
            "message_reactions is missing unique (message_id, user_id)"
        )

    foreign_keys = inspector.get_foreign_keys("message_reactions")
    expected_fks = {
        ("message_id", "messages", "id"),
        ("user_id", "users", "id"),
    }
    actual_fks = {
        (
            (fk.get("constrained_columns") or [None])[0],
            fk.get("referred_table"),
            (fk.get("referred_columns") or [None])[0],
        )
        for fk in foreign_keys
        if (fk.get("options") or {}).get("ondelete", "").upper() == "CASCADE"
    }
    if not expected_fks.issubset(actual_fks):
        raise RuntimeError(
            "message_reactions is missing expected cascading foreign keys"
        )

    check_constraints = inspector.get_check_constraints("message_reactions")
    allowed_check = next(
        (
            constraint
            for constraint in check_constraints
            if constraint.get("name") == "ck_message_reaction_allowed"
        ),
        None,
    )
    if not allowed_check or not all(
        emoji in (allowed_check.get("sqltext") or "")
        for emoji in ("❤️", "😂", "👍", "🔥", "😮", "😢")
    ):
        raise RuntimeError(
            "message_reactions is missing the allowed-reaction check constraint"
        )


def upgrade() -> None:
    if op.get_context().as_sql:
        op.create_table(
            "message_reactions",
            *_reaction_table_definition(),
            if_not_exists=True,
        )
        return

    bind = op.get_bind()
    if not inspect(bind).has_table("message_reactions"):
        op.create_table(
            "message_reactions",
            *_reaction_table_definition(),
            if_not_exists=bind.dialect.name == "postgresql",
        )

    # create_all() may already have made the table. Verify its shape instead
    # of silently accepting a partial or incompatible table.
    _validate_existing_table(bind)


def downgrade() -> None:
    # Do not drop this additive table: it may have pre-existed this revision
    # (for example, created by Base.metadata.create_all()), and it may contain
    # user reactions. Retaining it is safer than guessing ownership.
    pass
