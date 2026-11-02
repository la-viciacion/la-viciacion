"""game_igdb_id: the id of a game in IGDB, the backup source of the game catalogue

Revision ID: 049_game_igdb_id
Revises: 048_cost_items
Create Date: 2026-11-02 12:00:00.000000

RAWG can stop answering (it did for hours on 2026-11-02), so IGDB (Twitch's game database) can create and look up
games too. `games.igdb_id` keeps the IGDB id of a game the way `games.rawg_id` keeps RAWG's: data from outside, not
something derivable from `game_timers`. A game can have both, either or none (a game typed by hand).

Adds the nullable column `games.igdb_id` and an index on it (the duplicate check and the "already in the catalogue"
mark look games up by it). Additive only: no existing row is read or rewritten (NULL = not linked to IGDB).

Re-runnable: the column and the index are only created if missing.

Downgrade: drops the index and the column (the stored IGDB ids are lost; they are found again by linking the games).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '049_game_igdb_id'
down_revision: Union[str, None] = '048_cost_items'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'igdb_id'
INDEX = 'ix_games_igdb_id'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _indexes() -> set[str]:
    return {index['name'] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))
    if INDEX not in _indexes():
        op.create_index(INDEX, TABLE, [COLUMN])


def downgrade() -> None:
    if INDEX in _indexes():
        op.drop_index(INDEX, table_name=TABLE)
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
