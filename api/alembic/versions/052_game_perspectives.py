"""game_perspectives: how a game is seen and how it is played, from IGDB

Revision ID: 052_game_perspectives
Revises: 051_game_igdb_slug
Create Date: 2026-11-02 23:00:00.000000

IGDB says two more things about a game that RAWG's tags used to carry mixed with the rest (and the tag filter dropped as "how
it is shown" and "how many play it"): the **perspectives** (first person, third person, side view, top down...) and the
**game modes** (single player, multiplayer, co-operative, split screen, MMO). They are kept the way the other IGDB data is,
comma separated and in columns of their own, because some themes of the challenges need them: a first person shooter is a game
that is a shooter *and* is seen in first person.

  perspectives  IGDB's player perspectives
  game_modes    IGDB's game modes

Data from outside, not derivable from `game_timers`. NULL = IGDB was never asked for it; an empty text = IGDB has nothing.

Adds two nullable TEXT columns. Additive only: no existing row is read or rewritten (the link of the catalogue to IGDB
completes the games that have none).

Re-runnable: each column is only added if missing.

Downgrade: drops the columns (the stored data is lost; linking the games to IGDB fills it again).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '052_game_perspectives'
down_revision: Union[str, None] = '051_game_igdb_slug'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMNS = ('perspectives', 'game_modes')


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    present = _columns()
    for column in COLUMNS:
        if column not in present:
            op.add_column(TABLE, sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    present = _columns()
    for column in reversed(COLUMNS):
        if column in present:
            op.drop_column(TABLE, column)
