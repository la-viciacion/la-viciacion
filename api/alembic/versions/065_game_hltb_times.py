"""games: the other times of HowLongToBeat (main + extras, completionist, all styles)

Revision ID: 065_game_hltb_times
Revises: 064_game_early_access
Create Date: 2026-11-15 18:00:00.000000

The app only kept the main story of HowLongToBeat (`games.avg_time`). The game guide wants to place a player who plays for
100% by the completionist time, and later features can use the rest, so the other three times HowLongToBeat gives are added,
all in seconds like `avg_time`:

  games.time_extra   INT, nullable. Main story + extras.
  games.time_100     INT, nullable. Completionist (100%).
  games.time_all     INT, nullable. The average of all the ways of playing it.

NULL (or 0) = unknown: HowLongToBeat has no such time for the game, or it was never asked since this column exists. They are
filled when a game is created, when an admin syncs the times, and when a game is completed; no data is read or changed here.
Each step is only done if the column is missing, so the migration can be run again.

Downgrade drops the columns: the times are lost and the next HowLongToBeat sync brings them back.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '065_game_hltb_times'
down_revision: Union[str, None] = '064_game_early_access'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMNS = ('time_extra', 'time_100', 'time_all')


def _columns() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    for column in COLUMNS:
        if column not in _columns():
            op.add_column(TABLE, sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in COLUMNS:
        if column in _columns():
            op.drop_column(TABLE, column)
