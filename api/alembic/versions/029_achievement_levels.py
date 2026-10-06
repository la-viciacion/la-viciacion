"""achievements: the special level and the secret mark of the achievements that already exist

Revision ID: 029_achievement_levels
Revises: 028_achievement_special
Create Date: 2026-10-09 20:00:00.000000

The definitions in the code now say which achievements are special (and at which level: 1 silver, 2 gold,
3 purple) and which are secret, and a new installation creates them like that. This gives the same values to the
rows an installation already has, once.

Only what an admin has not touched is set: `special` only where it is still 0, `secret` only where it is still
false. What an admin chose in the panel is never overwritten. Rows this installation does not have (an
achievement that does not exist yet) are skipped: when the API creates them it uses the definition in the code.

No row is inserted or deleted and no schema changes. The lists below are a snapshot of the code at the time of
this migration: the code is the source for everything created from now on, and this file must not be edited
when the code changes later (an applied migration is immutable).

Re-runnable: it only sets the rows still at their default, so running it again changes nothing that an admin
has changed. Downgrade does nothing: the values are data an admin may have edited since, and the downgrade
of 028 drops the columns anyway.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '029_achievement_levels'
down_revision: Union[str, None] = '028_achievement_special'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPECIAL = (
    ('PLAYED_12_HOURS_DAY', 1),
    ('PLAYED_16_HOURS_DAY', 2),
    ('PLAYED_500_HOURS_GAME', 2),
    ('PLAYED_1000_HOURS_GAME', 3),
    ('PLAYED_500_HOURS', 1),
    ('PLAYED_1000_HOURS', 2),
    ('PLAYED_42_GAMES', 1),
    ('COMPLETED_25_GAMES', 1),
    ('COMPLETED_42_GAMES', 2),
    ('COMPLETED_100_GAMES', 3),
    ('PLAYED_200_DAYS', 1),
    ('PLAYED_300_DAYS', 2),
    ('PLAYED_365_DAYS', 3),
    ('STREAK_100_DAYS', 1),
    ('STREAK_200_DAYS', 1),
    ('STREAK_300_DAYS', 2),
    ('STREAK_365_DAYS', 3),
    ('PLAYED_1000_HOURS_GAME_LIFETIME', 1),
    ('PLAYED_1000_DAYS_LIFETIME', 1),
    ('PLAYED_2000_DAYS_LIFETIME', 2),
    ('PLAYED_5000_DAYS_LIFETIME', 3),
    ('PLAYED_2000_HOURS_LIFETIME', 1),
    ('PLAYED_5000_HOURS_LIFETIME', 2),
    ('PLAYED_10000_HOURS_LIFETIME', 3),
    ('PLAYED_500_GAMES_LIFETIME', 1),
    ('PLAYED_1000_GAMES_LIFETIME', 2),
    ('COMPLETED_500_GAMES_LIFETIME', 2),
    ('COMPLETED_1000_GAMES_LIFETIME', 3),
    ('JUST_IN_TIME', 1),
    ('RELEASE_DAY', 1),
    ('WORK_WEEK', 1),
    ('SAVED_BY_THE_BELL', 1),
    ('TEAMWORK', 1),
)

SECRET = (
    'JUST_IN_TIME',
    'EARLY_RISER',
    'NOCTURNAL',
    'SAVED_BY_THE_BELL',
    'PLAYED_10_GAMES_DAY',
)

achievements = sa.table('achievements', sa.column('key', sa.String), sa.column('special', sa.SmallInteger), sa.column('secret', sa.Boolean))


def upgrade() -> None:
    for key, level in SPECIAL:
        op.execute(achievements.update().where(achievements.c.key == key, achievements.c.special == 0).values(special=level))
    for key in SECRET:
        op.execute(achievements.update().where(achievements.c.key == key, achievements.c.secret == sa.false()).values(secret=sa.true()))


def downgrade() -> None:
    pass
