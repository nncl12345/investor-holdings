"""add_transaction_summary

Revision ID: 12a8e9f6b08f
Revises: 0b04110fe742
Create Date: 2026-04-20 15:44:37.642132
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "12a8e9f6b08f"
down_revision: str | None = "0b04110fe742"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The initial migration didn't create shares_owned / pct_owned / transaction_purpose
    # (those columns were added to the model later). Autogenerate emitted alter_column
    # against a dev DB that already had them; this hand-fixed version add_columns them
    # so the chain applies cleanly to a fresh database.
    op.add_column("filings", sa.Column("shares_owned", sa.Integer(), nullable=True))
    op.add_column("filings", sa.Column("pct_owned", sa.Float(), nullable=True))
    op.add_column("filings", sa.Column("transaction_purpose", sa.String(), nullable=True))
    op.add_column("filings", sa.Column("transaction_summary", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("filings", "transaction_summary")
    op.drop_column("filings", "transaction_purpose")
    op.drop_column("filings", "pct_owned")
    op.drop_column("filings", "shares_owned")
