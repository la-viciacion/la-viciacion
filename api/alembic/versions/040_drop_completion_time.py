"""drop_completion_time: remove the unused users_games.completion_time

Revision ID: 040_drop_completion_time
Revises: 039_game_dlc_link
Create Date: 2026-10-24 20:00:00.000000

Decision: `users_games.completion_time` is dropped. Migration 012 kept it as "a recorded fact", but the v2 code never
wrote it for a new completion (the time of a completion is derived from the sessions when it happens, see
`crud/time_entries.played_time_of_run`, and shown in the notice only) and nothing read it to show or compute
anything. A backup of the production database taken on 2026-10-22 (revision 037) had it empty in all 827
entries, 197 of them completed. It also went against "do not store what can be derived".

What it loses: the values that migration 011 copies from a v1 backup (a v1 -> v2 upgrade of a database that
had them) and those an import file carried; nothing in the app showed them. It does not refuse on data: that
is the decision recorded here. As with every migration, take a fresh backup before it runs.

Re-runnable: the column is only dropped if it is there.

Downgrade: adds the column back, empty (NULL); the dropped values are not restored.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '040_drop_completion_time'
down_revision: Union[str, None] = '039_game_dlc_link'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users_games'
COLUMN = 'completion_time'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)


def downgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Integer(), nullable=True))
