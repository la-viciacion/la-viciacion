"""restore the 2023 and 2024 library entries archived by migration 005

Revision ID: 011_restore_old_library
Revises: 010_drop_clockify
Create Date: 2026-09-30 12:00:00.000000

Migration 005 moved the per-year library tables out of the active schema
(`_archived_users_games_historical`, `_archived_users_games_2024`). Their sessions
stayed in game_timers, so every 2023/2024 session had no library entry (the admin
panel showed games with sessions and 0 players). This puts those entries back in
users_games, whose `season` is derived from `started_date`.

What is imported (checked against a copy of production: it covers exactly the 485
(user, game, season) pairs that have sessions before 2025):

- season 2023: rows of `_archived_users_games_historical` started before 2024.
- season 2024: rows of `_archived_users_games_2024` started in 2024.

What is NOT imported, on purpose:

- the rows of `_archived_users_games_historical` started in 2024: an older snapshot
  of the same season, superseded by `_archived_users_games_2024`;
- archived rows whose started_date is not in the season they would land in (one row
  dated 2025-01-01 sits in the 2024 archive; 2025 already has its own library);
- rows whose user or game no longer exists.

Values are copied verbatim (platform, completion, score, times); nothing is invented
or corrected, including 9 old completions whose completed_date is empty or in another
year. The archived ids are not reused. The archives themselves are left untouched.

Safe to re-run: an entry is only inserted when users_games has no row for the same
(user, game, platform, season), platform NULL included (a plain unique key would let
NULL platforms repeat). It refuses to run if the source itself repeats a key.

Downgrade removes the users_games rows that equal an archived row (same user, game,
platform and start date) in seasons before 2025; entries created by hand since are kept.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '011_restore_old_library'
down_revision: Union[str, None] = '010_drop_clockify'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (archive table, condition on the archived row `a` that selects what to import)
SOURCES = (
    ('_archived_users_games_historical', 'YEAR(a.started_date) < 2024'),
    ('_archived_users_games_2024', 'YEAR(a.started_date) = 2024'),
)

COLUMNS = 'user_id, game_id, started_date, platform, completed, completed_date, score, played_time, completion_time'


def _existing_sources(bind) -> list:
    tables = set(sa.inspect(bind).get_table_names())
    return [(table, where) for table, where in SOURCES if table in tables]


def _check_no_repeated_keys(bind, sources) -> None:
    for table, where in sources:
        repeated = bind.execute(sa.text(
            f'SELECT a.user_id, a.game_id, COALESCE(a.platform, \'\'), YEAR(a.started_date), COUNT(*) '
            f'FROM {table} a WHERE {where} '
            f'GROUP BY a.user_id, a.game_id, COALESCE(a.platform, \'\'), YEAR(a.started_date) HAVING COUNT(*) > 1 LIMIT 5'
        )).fetchall()
        if repeated:
            raise RuntimeError(
                f'{table} repeats (user, game, platform, season) keys, e.g. {[tuple(r) for r in repeated]}; '
                'decide by hand which one to keep before running this migration'
            )


def _import_sql(table: str, where: str) -> str:
    return (
        f'INSERT INTO users_games ({COLUMNS}) '
        f'SELECT a.user_id, a.game_id, a.started_date, a.platform, a.completed, a.completed_date, a.score, '
        f'a.played_time, a.completion_time FROM {table} a '
        f'WHERE {where} AND a.started_date IS NOT NULL '
        'AND EXISTS (SELECT 1 FROM users u WHERE u.id = a.user_id) '
        'AND EXISTS (SELECT 1 FROM games g WHERE g.id = a.game_id) '
        'AND NOT EXISTS (SELECT 1 FROM users_games ug WHERE ug.user_id = a.user_id AND ug.game_id = a.game_id '
        'AND ug.platform <=> a.platform AND ug.season = YEAR(a.started_date)) '
        'ORDER BY a.started_date, a.id'
    )


def upgrade() -> None:
    bind = op.get_bind()
    sources = _existing_sources(bind)

    # 1. verify before changing anything (a database without the archives has nothing to restore)
    _check_no_repeated_keys(bind, sources)

    # 2. import, oldest source first
    for table, where in sources:
        op.execute(_import_sql(table, where))


def downgrade() -> None:
    bind = op.get_bind()
    for table, where in _existing_sources(bind):
        op.execute(
            f'DELETE ug FROM users_games ug JOIN {table} a ON a.user_id = ug.user_id AND a.game_id = ug.game_id '
            f'AND a.platform <=> ug.platform AND a.started_date = ug.started_date '
            f'WHERE ug.season < 2025 AND {where}'
        )
