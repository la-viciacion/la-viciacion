"""game_igdb_data: what IGDB says about a game beyond its genres, for the statistics

Revision ID: 050_game_igdb_data
Revises: 049_game_igdb_id
Create Date: 2026-11-02 18:00:00.000000

IGDB describes a game with more than RAWG's genres and tags, and the statistics can use all of it. Four columns keep it,
comma separated like `genres` and `tags` (a name with a comma loses it when it is stored), and apart from `tags` on
purpose: `tags` are RAWG's vocabulary and the RAWG sync reads an empty one as "never asked", and the filter that cleans
them is written for RAWG's.

  themes       IGDB's themes: Fantasy, Horror, Survival, Open world...
  keywords     IGDB's keywords: what the community says the game is (Roguelike, Souls-like, Pixel art...); dozens a game
  franchises   the franchise it belongs to (Star Wars, The Legend of Zelda...)
  collections  the series it is part of

Data from outside, like `rawg_id` or `genres`, not derivable from `game_timers`. NULL = IGDB was never asked about the
game; an empty text = IGDB has nothing of it (so it is not asked again, like `tags`).

Adds four nullable TEXT columns. Additive only: no existing row is read or rewritten.

Re-runnable: each column is only added if missing.

Downgrade: drops the columns (the stored IGDB data is lost; linking the games to IGDB fills it again).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '050_game_igdb_data'
down_revision: Union[str, None] = '049_game_igdb_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMNS = ('themes', 'keywords', 'franchises', 'collections')


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
