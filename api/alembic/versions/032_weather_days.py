"""weather_days: the weather of a past day at a place, so that Open-Meteo is asked for each day once

Revision ID: 032_weather_days
Revises: 031_game_tags
Create Date: 2026-10-07 22:20:00.000000

The weather achievements need what the weather was while a player was playing. Open-Meteo gives it for free and
without a key, but a day is over for good once it has passed, so it is kept and never asked for twice:

  weather_days   place VARCHAR(24)  the place rounded to two decimals ("40.42,-3.70"), about a kilometre
                 day DATE
                 codes VARCHAR(120)  the 24 WMO weather codes of the day's hours, comma separated ("" for a missing one)
                 fetched_at DATETIME
                 primary key (place, day)

It is outside data, not something derived from the sessions, which is why it may be stored. Only complete days that are
over are kept; today is asked for again each time.

Purely additive: a new table, nothing existing is read, rewritten or refused. No foreign keys: it belongs to no player.

Re-runnable: the table is only created if it is missing. Downgrade drops it (it is filled again from Open-Meteo).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '032_weather_days'
down_revision: Union[str, None] = '031_game_tags'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'weather_days'


def _has_table() -> bool:
    return TABLE in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column('place', sa.String(24), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('codes', sa.String(120), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('place', 'day'),
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE)
