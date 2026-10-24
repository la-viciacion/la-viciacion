"""game_parent: the base game of a DLC

Revision ID: 038_game_parent
Revises: 037_user_notifications
Create Date: 2026-10-24 12:00:00.000000

RAWG tells which games are additions (DLCs, expansions, editions) of another one. `games.parent_rawg_id` keeps the
RAWG id of that base game so the app can mark the game as a DLC and link to its base. It is data from outside
(like `rawg_id` or `genres`), not something derivable from `game_timers`. It is the RAWG id and not a foreign key
to `games.id` because the base game may not be in the catalogue (games added before this column existed).

Adds the nullable column `games.parent_rawg_id`. Additive only: no existing row is read or rewritten (NULL = not
a DLC, or not asked yet; the RAWG sync fills it for the games it processes).

Re-runnable: the column is only added if missing.

Downgrade: drops the column (the stored base ids are lost; RAWG gives them again on the next sync).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '038_game_parent'
down_revision: Union[str, None] = '037_user_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'games'
COLUMN = 'parent_rawg_id'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
