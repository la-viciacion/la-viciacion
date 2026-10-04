"""users_games.abandoned_at: let a player mark a game of the season as abandoned

Revision ID: 023_abandoned_at
Revises: 022_audit_log
Create Date: 2026-10-04 20:00:00.000000

A game that is not going to be finished can be marked as abandoned, which says so instead of leaving it
"in progress" for ever. This stores only the decision, when it was taken (NULL = not abandoned). Whether the
entry is *still* abandoned is derived when asked: playing the game again after that moment resumes it, so
nothing has to be rewritten when a session is added.

Purely additive: a nullable column, every existing row is NULL (not abandoned). Nothing is rewritten or refused.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the marks are lost and every
entry goes back to being in progress or completed).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '023_abandoned_at'
down_revision: Union[str, None] = '022_audit_log'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users_games'
COLUMN = 'abandoned_at'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
