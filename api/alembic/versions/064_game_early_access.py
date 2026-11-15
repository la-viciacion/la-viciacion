"""games.early_access_date: the day a game went into early access

Revision ID: 064_game_early_access
Revises: 063_ai_wallet_unlimited
Create Date: 2026-11-15 12:00:00.000000

Players play games that are still in early access, and the app wants to say so, with the day it began, until the official launch
(`release_date`) is reached. One column is added:

  games.early_access_date   DATE, nullable. NULL = the game is not known to have had an early access. It is filled from IGDB (when a
                            game is created, when it is resynced and by the daily refresh) or by an admin. Whether a game *is* in
                            early access is never stored: it is derived from this day and `release_date` (crud/early_access.py), so
                            reaching the official day needs no job to take any mark off.

No data is read or changed. The step is only done if the column is missing, so it can be run again.

Downgrade drops the column: the early access days are lost, and the next IGDB refresh or resync brings them back.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '064_game_early_access'
down_revision: Union[str, None] = '063_ai_wallet_unlimited'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'early_access_date'


def _columns() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Date(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
