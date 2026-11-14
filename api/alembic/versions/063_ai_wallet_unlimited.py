"""user_settings: a player an admin has taken the wallet limit off

Revision ID: 063_ai_wallet_unlimited
Revises: 062_ach_description
Create Date: 2026-11-14 18:00:00.000000

The wallet of the group's AI key (060) used to be off until the first contribution was written down. From now on it is always on: a
player with nothing put in has a balance of 0 and cannot use the group's key until an admin writes down a contribution for them. One
new column lets an admin take that limit off one player (their balance is then not checked):

  ai_wallet_unlimited   1 = this player is not stopped by the wallet; NULL or 0 = the wallet applies. Only an admin sets it; the
                        player cannot (it is not part of what they may patch).

Nullable and NULL everywhere: nothing existing is rewritten, read or refused. What a player pays with their own key is never
limited by the wallet.

Re-runnable: the column is only added if it is missing.

Downgrade drops the column: the exemptions are lost and the wallet applies to everybody.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '063_ai_wallet_unlimited'
down_revision: Union[str, None] = '062_ach_description'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMN = 'ai_wallet_unlimited'


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _existing():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=True))


def downgrade() -> None:
    if COLUMN in _existing():
        op.drop_column(TABLE, COLUMN)
