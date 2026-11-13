"""ai_wallet_entries: what each player puts in for the group's AI key (a wallet per player)

Revision ID: 060_ai_wallet
Revises: 059_ai_budget_zero
Create Date: 2026-11-13 12:00:00.000000

The group pays the AI with one key and one account. To share it fairly, every player's contribution is written down and what they
spend of the group's key is taken from it: their balance is what they put in minus what they spent (summed from `ai_usage` when
asked, never stored). This migration adds the one thing that cannot be derived from anything else, the contributions: one row per
top-up, with the amount in millionths of a dollar (the unit of `ai_usage.cost_micros`). The amount can be negative: a refund or a
correction is a new row, so the record is never edited (the table is a ledger, like `ai_usage`).

  user_id     whose contribution it is; NULL when the account was deleted (the money stays in the group's total)
  amount_micros  signed, never 0
  note        free text, what the contribution was
  created_by  the admin that wrote it down (NULL if deleted)

Additive only: a new table, nothing existing is touched, read or refused. Both foreign keys are ON DELETE SET NULL, so deleting an
account is not refused for its contributions nor erases them.

Re-runnable: the table and its index are only created if missing.

Downgrade: drops the table (the contributions are lost; the balances go back to the monthly budgets alone).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '060_ai_wallet'
down_revision: Union[str, None] = '059_ai_budget_zero'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'ai_wallet_entries'
INDEX = 'ix_ai_wallet_user'


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            TABLE,
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('amount_micros', sa.BigInteger(), nullable=False),
            sa.Column('note', sa.String(length=200), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ai_wallet_user', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_ai_wallet_by', ondelete='SET NULL'),
        )
    if INDEX not in {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, ['user_id'])


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
