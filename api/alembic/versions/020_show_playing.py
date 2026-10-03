"""user_settings.show_playing: let a player choose whether the others see them playing

Revision ID: 020_show_playing
Revises: 019_game_scores
Create Date: 2026-10-03 20:00:00.000000

The group can see who is playing right now (the chip in the navbar). This adds the personal
preference that lets a player stay out of it: NULL = the default, which lives in code (shown),
0 = hidden, 1 = shown.

Purely additive: a nullable column on a table whose rows are all NULL-for-this-setting, so
everybody keeps being shown, as the default says. Nothing is rewritten or refused.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the preference is
lost and everybody is shown again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '020_show_playing'
down_revision: Union[str, None] = '019_game_scores'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMN = 'show_playing'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
