"""achievements.special: the level (1 to 3) of a special achievement, which gives it an aura of its own colour

Revision ID: 028_achievement_special
Revises: 027_achievement_valid_from
Create Date: 2026-10-08 20:00:00.000000

An achievement can be special at one of three levels, and each level is a colour: 1 silver, 2 gold, 3 purple. The
level is shown as an aura wherever the achievement appears and the announcement says it is special. It is
independent of `achievements.secret` (hidden until unlocked): an achievement can be secret, special, both or
neither.

This adds the level: `achievements.special`, SMALLINT NOT NULL, default 0 (an ordinary achievement). Every
existing achievement is therefore ordinary, so nothing changes for what is already in play; an admin sets the
level of the ones that are special. This migration does not insert or rewrite anything.

Purely additive: nothing is rewritten, refused or deleted.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the levels are lost).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '028_achievement_special'
down_revision: Union[str, None] = '027_achievement_valid_from'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'achievements'
COLUMN = 'special'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.SmallInteger(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
