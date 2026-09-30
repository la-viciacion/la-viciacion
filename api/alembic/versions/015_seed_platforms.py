"""seed the platform catalogue on a database that has none

Revision ID: 015_seed_platforms
Revises: 014_user_settings
Create Date: 2026-09-30 18:00:00.000000

`platform_tags` is the list of platforms a session or a library entry can be played on
(`GET /utils/platforms`; sessions are validated against it). It has no admin screen, and
on the databases that come from v1 it was filled by hand with ids that were Clockify
tags. A new deployment starts with the table empty, and then nobody can start a timer,
so this data migration gives it a default catalogue with readable ids.

Only when the table is empty: a database that already has platforms, whatever they are,
is left exactly as it is. Nothing is updated or deleted, and running it again does
nothing.

Downgrade: removes those default rows again, but only the ones nothing refers to (no
session or library entry uses them), so it can never orphan data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '015_seed_platforms'
down_revision: Union[str, None] = '014_user_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLATFORMS = [
    ('pc', 'PC'),
    ('steam-deck', 'Steam Deck'),
    ('ps5', 'PlayStation 5'),
    ('ps4', 'PlayStation 4'),
    ('ps3', 'PlayStation 3'),
    ('ps2', 'PlayStation 2'),
    ('ps1', 'PlayStation'),
    ('xbox', 'Xbox'),
    ('switch', 'Nintendo Switch'),
    ('switch-2', 'Nintendo Switch 2'),
    ('3ds', 'Nintendo 3DS'),
    ('ds', 'Nintendo DS'),
    ('mobile', 'Móvil'),
    ('arcade', 'Recreativa'),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT COUNT(*) FROM platform_tags')).scalar():
        return
    platform_tags = sa.table('platform_tags', sa.column('id', sa.String), sa.column('name', sa.String))
    op.bulk_insert(platform_tags, [{'id': id_, 'name': name} for id_, name in PLATFORMS])


def downgrade() -> None:
    bind = op.get_bind()
    for id_, _ in PLATFORMS:
        in_use = bind.execute(
            sa.text(
                'SELECT (SELECT COUNT(*) FROM game_timers WHERE platform = :id) '
                '+ (SELECT COUNT(*) FROM users_games WHERE platform = :id)'
            ),
            {'id': id_},
        ).scalar()
        if not in_use:
            bind.execute(sa.text('DELETE FROM platform_tags WHERE id = :id'), {'id': id_})
