"""user_settings.forgotten_timer_telegram / forgotten_timer_push: choose where the forgotten-timer notice goes

Revision ID: 024_forgotten_timer_channels
Revises: 023_abandoned_at
Create Date: 2026-10-04 12:00:00.000000

First notice a user can switch on or off, per channel: the reminder about a timer that has been
running for too long. Two nullable booleans, one per channel (Telegram, push to the user's
devices): NULL = the default, which lives in code (on), 0 = off, 1 = on. The notice is off for
a user when both channels are off; the hours it waits for stay in `forgotten_timer_hours`.

Purely additive: nullable columns on a table whose rows are all NULL-for-these-settings, so
everybody keeps receiving the notice on every channel they can be reached by, as before.
Nothing is rewritten or refused.

Re-runnable: each column is only added if it is missing. Downgrade drops both (the choices are
lost and the notice reaches everybody again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '024_forgotten_timer_channels'
down_revision: Union[str, None] = '023_abandoned_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = ('forgotten_timer_telegram', 'forgotten_timer_push')


def _columns() -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    for column in COLUMNS:
        if column not in _columns():
            op.add_column(TABLE, sa.Column(column, sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column in COLUMNS:
        if column in _columns():
            op.drop_column(TABLE, column)
