"""achievements: the special level and the secret mark after the review of the whole catalogue

Revision ID: 033_achievement_review
Revises: 032_weather_days
Create Date: 2026-10-10 20:00:00.000000

The catalogue was reviewed one by one: some achievements are now secret, some change their level (1 silver,
2 gold, 3 purple), and the ones about the world outside the app (which were created before they had a level) get
theirs. The definitions in the code say so and a new installation creates them like that; this brings the rows an
installation already has to the same values, once.

Like 029, only what an admin has not touched is set: a `special` only where it still holds the value the old
definition gave it, a `secret` only where it is still false. What an admin chose in the panel is never
overwritten. Rows this installation does not have are skipped (when the API creates them it uses the code).

No row is inserted or deleted and no schema changes. The lists below are a snapshot of the code at the time of
this migration and the file must not be edited when the code changes later (an applied migration is immutable).

Re-runnable: it only changes the rows still at the old value, so running it again changes nothing. Downgrade does
nothing: the values are data an admin may have edited since.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '033_achievement_review'
down_revision: Union[str, None] = '032_weather_days'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (key, the level the old definition gave it, the level now)
SPECIAL = (
    ('PLAYED_100_HOURS_GAME', 0, 1),
    ('PLAYED_50_GAMES', 0, 1),
    ('PLAYED_100_GAMES', 0, 2),
    ('PLAYED_10_GAMES_DAY', 0, 1),
    ('PLAYED_1000_HOURS_GAME_LIFETIME', 1, 2),
    ('STORM_LIFETIME', 0, 1),
    ('HORROR_FOG_LIFETIME', 0, 2),
    ('LEAP_DAY_LIFETIME', 0, 1),
    ('LUNAR_ECLIPSE_LIFETIME', 0, 3),
    ('SOLAR_ECLIPSE_LIFETIME', 0, 3),
    ('BIRTH_YEAR_GAME_LIFETIME', 0, 1),
)

SECRET = (
    'PLAYED_12_HOURS_DAY',
    'PLAYED_4_HOURS_SESSION',
    'COMPLETED_42_GAMES',
    'PLAYED_200_DAYS',
    'PLAYED_300_DAYS',
    'PLAYED_365_DAYS',
    'COMPLETED_IN_A_DAY',
    'TEAMWORK',
    'HAPPY_NEW_YEAR',
)

achievements = sa.table('achievements', sa.column('key', sa.String), sa.column('special', sa.SmallInteger), sa.column('secret', sa.Boolean))


def upgrade() -> None:
    for key, old, new in SPECIAL:
        if old != new:
            op.execute(achievements.update().where(achievements.c.key == key, achievements.c.special == old).values(special=new))
    for key in SECRET:
        op.execute(achievements.update().where(achievements.c.key == key, achievements.c.secret == sa.false()).values(secret=sa.true()))


def downgrade() -> None:
    pass
