"""user_settings: the monthly AI budget an admin gives a player, for what the group's key pays

Revision ID: 057_ai_budget
Revises: 056_user_ai_key
Create Date: 2026-11-12 20:00:00.000000

The group's key is a shared quota, so what it pays for is limited by a budget per month (admin settings `ai.group_budget_month`
for everybody and `ai.user_budget_month` for each player, in whole dollars, 0 = no limit). One new column on the player's personal
settings lets an admin give one player more or less than that default:

  ai_group_budget_usd   whole dollars a month this player may spend of the group's key; NULL = the default of the settings applies,
                        0 = no limit. Only an admin sets it; the player cannot (it is not part of what they may patch).

Nullable and NULL everywhere: nothing existing is rewritten, read or refused. What a player pays with their own key never
counts against it.

Re-runnable: the column is only added if it is missing.

Downgrade drops the column: the individual budgets are lost and the default applies to everybody.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '057_ai_budget'
down_revision: Union[str, None] = '056_user_ai_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMN = 'ai_group_budget_usd'


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _existing():
        op.add_column(TABLE, sa.Column(COLUMN, sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    if COLUMN in _existing():
        op.drop_column(TABLE, COLUMN)
