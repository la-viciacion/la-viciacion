"""games.tags: RAWG's tags of a game

Revision ID: 031_game_tags
Revises: 030_user_place_birth
Create Date: 2026-10-07 22:10:00.000000

RAWG describes a game with genres (Action, RPG, Shooter...) and with tags (Horror, Singleplayer, Star Wars...).
There is no Horror genre, only a Horror tag, and an achievement needs to know which games are horror games, so the
tags are kept: one comma separated text, like `genres`.

Purely additive: a nullable column, NULL for every game that exists. Nothing is rewritten or refused. The games
get their tags the next time RAWG is asked about them (the sync of the admin panel fills the ones that have none),
and the ones created from now on come with them.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the tags are lost; RAWG has them again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '031_game_tags'
down_revision: Union[str, None] = '030_user_place_birth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'tags'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
