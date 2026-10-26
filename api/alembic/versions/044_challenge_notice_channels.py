"""user_settings.challenge_notices_* / challenge_reminders_*: choose where the notices about one's challenges go

Revision ID: 044_challenge_notice_channels
Revises: 043_challenge_schedules
Create Date: 2026-10-26 15:00:00.000000

Two more notices a user can switch on or off, per channel, like the forgotten timer (migration 024) and the release
day of a wished game (041):

  challenge_notices_telegram / challenge_notices_push    what concerns the player in their challenges: being
                                                         challenged to a duel, a duel turned down, how a proposal
                                                         was answered and how their challenges ended
  challenge_reminders_telegram / challenge_reminders_push  a reminder when a challenge has two days left and the
                                                         player has not met their part

Four nullable booleans: NULL = the default, which lives in code (the first notice on, the reminders off), 0 = off,
1 = on. A notice is not sent to a user when both of its channels are off.

Purely additive: nullable columns on a table whose rows are all NULL-for-these-settings, so nobody has chosen
anything yet and everybody gets the defaults. Nothing is rewritten or refused.

Re-runnable: each column is only added if it is missing. Downgrade drops the four (the choices are lost and the
notices go back to their defaults).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '044_challenge_notice_channels'
down_revision: Union[str, None] = '043_challenge_schedules'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = (
    'challenge_notices_telegram', 'challenge_notices_push',
    'challenge_reminders_telegram', 'challenge_reminders_push',
)


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
