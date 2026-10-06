"""achievements.valid_from_season: the first season in which an achievement can be earned

Revision ID: 027_achievement_valid_from
Revises: 026_achievement_secret
Create Date: 2026-10-07 20:00:00.000000

An achievement can be made to take effect from a given season: before it, nobody earns it, nothing is
announced about it, the recalculation leaves what is stored exactly as it is and the group's page does not
show it. For an achievement with no season limit (whose key ends in _LIFETIME) it also means that only what was
done from that season on counts. It exists so that new achievements can be in the catalogue, active, and still
only begin to count when a season starts.

This adds the column: `achievements.valid_from_season`, NOT NULL, default 2023 (the first season of the app).
Every existing achievement is therefore valid from 2023, so nothing changes for what is already in play.
Achievements added later get the season their definition in code says (`since`), and an admin can change it.
This migration does not insert anything.

Purely additive: nothing is rewritten, refused or deleted.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the seasons are lost and every
achievement is in effect again from the first one).

From this migration on, an achievement the code adds to an installation that already has some is **active**
(until then, see 025, it started switched off): the season it is valid from is what keeps it from counting yet.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '027_achievement_valid_from'
down_revision: Union[str, None] = '026_achievement_secret'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'achievements'
COLUMN = 'valid_from_season'
FIRST_SEASON = '2023'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.SmallInteger(), nullable=False, server_default=sa.text(FIRST_SEASON)))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
