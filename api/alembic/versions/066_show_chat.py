"""user_settings.show_chat: let a player hide the chat button

Revision ID: 066_show_chat
Revises: 065_game_hltb_times
Create Date: 2026-11-15 20:00:00.000000

The chat button is on for everybody while an admin has the chat on. This adds the personal preference that lets a
player hide it from their own screens: NULL = the default, which lives in code (shown), 0 = hidden, 1 = shown.

Purely additive: a nullable column on a table whose rows are all NULL-for-this-setting, so everybody keeps seeing the
button, as the default says. Nothing is rewritten or refused.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the preference is lost and the button
is shown to everybody again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '066_show_chat'
down_revision: Union[str, None] = '065_game_hltb_times'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMN = 'show_chat'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
