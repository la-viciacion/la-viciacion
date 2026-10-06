"""achievements.active: let an admin choose which achievements are in play

Revision ID: 025_achievement_active
Revises: 024_forgotten_timer_channels
Create Date: 2026-10-06 20:00:00.000000

An achievement can be switched off: while it is, nobody earns it, nothing is announced about it, the
recalculation leaves it alone and the group's page does not show it (unless a player already has it). It
exists so that new achievements can be added to the catalogue and only start to count when an admin
decides (for instance, at the start of a season).

This adds the switch: `achievements.active`, NOT NULL, default 1. Every existing achievement is **active**,
so nothing changes for what is already in play. Achievements added later to an installation that already has
some start switched off (the code decides that when it creates them, see `populate_achievements`); this
migration does not insert anything.

Purely additive: nothing is rewritten, refused or deleted.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the switches are lost and every
achievement is in play again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '025_achievement_active'
down_revision: Union[str, None] = '024_forgotten_timer_channels'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'achievements'
COLUMN = 'active'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
