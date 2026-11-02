"""game_igdb_slug: the address of a game's page in IGDB

Revision ID: 051_game_igdb_slug
Revises: 050_game_igdb_data
Create Date: 2026-11-02 21:00:00.000000

A page of a game is `rawg.io/games/<slug>` or `igdb.com/games/<slug>` and a slug is each site's own: `games.slug` is RAWG's
(or, for the games IGDB created before this column, IGDB's), so a game with both ids had no way to say where its IGDB page
is, and the links of the notices and of the game page could only be RAWG's. `games.igdb_slug` keeps IGDB's, so IGDB, the main
source, is the one the app links to and RAWG's page is the fallback.

Adds the nullable column `games.igdb_slug`. Additive only: no existing row is read or rewritten (NULL = not known yet; the
link of the catalogue to IGDB and the resync of a game fill it, and a game IGDB created before this column keeps IGDB's slug
in `slug`, which the code still reads as IGDB's when the game has no RAWG id).

Re-runnable: the column is only added if missing.

Downgrade: drops the column (the stored slugs are lost; linking the games to IGDB fills them again).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '051_game_igdb_slug'
down_revision: Union[str, None] = '050_game_igdb_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'igdb_slug'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(255), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
