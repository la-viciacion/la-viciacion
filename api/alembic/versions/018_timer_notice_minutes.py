"""user_settings.timer_notice_minutes: how often the running-timer notification is refreshed

Revision ID: 018_timer_notice_minutes
Revises: 017_password_resets
Create Date: 2026-10-01 21:00:00.000000

Adds the second personal preference: every how many minutes the pinned push notification of a
running timer is refreshed (NULL = the default, which lives in code). Whole minutes, 10-120: the
CHECK refuses anything below 10 on purpose, push services throttle senders that refresh too
often (MariaDB validates CHECK constraints on insert/update only).

Purely additive: a nullable column on a table whose rows are all NULL-for-this-setting, so
everybody keeps behaving as before. The CHECK is added after the column and cannot fail on
existing data (every value is NULL).

Re-runnable: each step first checks whether it is already done. Downgrade drops the constraint
and the column (the preference is lost and reverts to the default).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '018_timer_notice_minutes'
down_revision: Union[str, None] = '017_password_resets'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMN = 'timer_notice_minutes'
CHECK = 'ck_user_settings_notice_minutes'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _has_check() -> bool:
    return CHECK in {c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.SmallInteger(), nullable=True))
    if not _has_check():
        op.create_check_constraint(CHECK, TABLE, f'{COLUMN} IS NULL OR {COLUMN} BETWEEN 10 AND 120')


def downgrade() -> None:
    if _has_check():
        op.drop_constraint(CHECK, TABLE, type_='check')
    if _has_column():
        op.drop_column(TABLE, COLUMN)
