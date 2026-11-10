"""user_settings game ids: the ids a player has on Nintendo, Xbox, PlayStation, Steam and Discord

Revision ID: 054_user_game_ids
Revises: 053_game_created_at
Create Date: 2026-11-10 20:00:00.000000

Five new personal data, all optional, so the friends can find each other where they play:

  nintendo_id, xbox_id, playstation_id, steam_id, discord_id   free text as each service names a person (a Nintendo
                                                                friend code, a gamertag, a PSN id, a Steam friend code
                                                                or profile name, a Discord username), at most 64
                                                                characters. The app does not check them against any
                                                                service.

Purely additive: five nullable columns on a table whose rows are all NULL for them, which means "not set". Nothing is
rewritten or refused.

Re-runnable: each column is only added if it is missing. Downgrade drops them (the ids are lost).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '054_user_game_ids'
down_revision: Union[str, None] = '053_game_created_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = ('nintendo_id', 'xbox_id', 'playstation_id', 'steam_id', 'discord_id')


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _existing()
    for name in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _existing()
    for name in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
