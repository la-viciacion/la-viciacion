"""achievements.secret: let an admin mark achievements that are announced without saying which

Revision ID: 026_achievement_secret
Revises: 025_achievement_active
Create Date: 2026-10-06 22:00:00.000000

A secret achievement is special: when somebody unlocks it, the group is only told that they unlocked a hidden
achievement (not which, nor the game), and the player gets the whole notice privately. It is shown with a
golden aura wherever it appears.

This adds the mark: `achievements.secret`, NOT NULL, default 0. Every existing achievement is **not secret**,
so nothing changes for what is already in play; an admin marks the ones that are.

Purely additive: nothing is rewritten, refused or deleted.

Re-runnable: the column is only added if it is missing. Downgrade drops it (the marks are lost and every
achievement is announced in full again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '026_achievement_secret'
down_revision: Union[str, None] = '025_achievement_active'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'achievements'
COLUMN = 'secret'


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
