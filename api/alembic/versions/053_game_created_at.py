"""game_created_at: when a game was added to the catalogue

Revision ID: 053_game_created_at
Revises: 052_game_perspectives
Create Date: 2026-11-02 23:30:00.000000

The catalogue never said when a game was added. It is needed by the hourly job that links to IGDB the games created from
RAWG while IGDB could not answer: only the games added in the last days are its business, the older ones are linked by the
admin in batches (and, if asked, have their data replaced by IGDB's), and a job that linked the whole catalogue by itself
would take that away.

Adds the nullable column `games.created_at`. Additive only: no existing row is read or rewritten (NULL = added before this
column, which the job never touches). The app fills it when it creates a game.

Re-runnable: the column is only added if missing.

Downgrade: drops the column (the dates are lost).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '053_game_created_at'
down_revision: Union[str, None] = '052_game_perspectives'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'created_at'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
