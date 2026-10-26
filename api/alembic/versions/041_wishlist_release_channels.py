"""user_settings.wishlist_release_telegram / wishlist_release_push: choose where the release-day notice goes

Revision ID: 041_wishlist_release_channels
Revises: 040_drop_completion_time
Create Date: 2026-10-26 12:00:00.000000

Second notice a user can switch on or off, per channel (after the forgotten timer, migration 024): the private
notice of the day a game of their wishlist comes out. Two nullable booleans, one per channel (Telegram, push to
the user's devices): NULL = the default, which lives in code (on), 0 = off, 1 = on. The notice is off for a user
when both channels are off.

Purely additive: nullable columns on a table whose rows are all NULL-for-these-settings, so nobody has chosen
anything yet and everybody gets the default. Nothing is rewritten or refused.

Re-runnable: each column is only added if it is missing. Downgrade drops both (the choices are lost and the notice
reaches everybody again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '041_wishlist_release_channels'
down_revision: Union[str, None] = '040_drop_completion_time'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = ('wishlist_release_telegram', 'wishlist_release_push')


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
