"""season becomes a generated column derived from the row's date

Revision ID: 008_season_generated
Revises: 007_users_unique_email
Create Date: 2026-09-29 18:00:00.000000

`season` used to be stored next to the date it is derived from, so the two
could disagree. It is now computed by the database from that date and can no
longer be written:

    users_games.season         = YEAR(started_date)
    game_timers.season         = YEAR(start_time)
    users_achievements.season  = YEAR(date)

The columns keep their name and stay filterable and indexable, so queries and
the unique keys ("one entry per user/game/platform/season", "one achievement
per user and season") keep working. VIRTUAL columns are used: adding one does
not rebuild the table.

MariaDB cannot roll back DDL, so every step checks what already exists and the
migration can simply be run again if it was interrupted. It refuses to touch
anything if a row disagrees with its date (nothing is rewritten silently) or
if the new unique keys would be violated.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '008_season_generated'
down_revision: Union[str, None] = '007_users_unique_email'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table -> (date column, generation expression)
TABLES = {
    'users_games': ('started_date', 'YEAR(started_date)'),
    'game_timers': ('start_time', 'YEAR(start_time)'),
    'users_achievements': ('date', 'YEAR(`date`)'),
}


def _season_state(bind, table: str) -> str:
    """'missing' | 'plain' | 'generated'"""
    row = bind.execute(
        sa.text(
            'SELECT generation_expression FROM information_schema.columns '
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = 'season'"
        ),
        {'t': table},
    ).first()
    if row is None:
        return 'missing'
    return 'generated' if row[0] else 'plain'


def _index_names(bind, table: str) -> set:
    return {i['name'] for i in sa.inspect(bind).get_indexes(table)}


def _check_consistent(bind, table: str, date_col: str) -> None:
    col = f'`{date_col}`'
    missing = bind.execute(sa.text(f'SELECT COUNT(*) FROM {table} WHERE {col} IS NULL')).scalar()
    mismatch = bind.execute(
        sa.text(f'SELECT COUNT(*) FROM {table} WHERE season IS NULL OR season <> YEAR({col})')
    ).scalar()
    if missing or mismatch:
        raise RuntimeError(
            f'{table}: {missing} rows without {date_col} and {mismatch} rows whose season differs from '
            f'YEAR({date_col}). Fix them first, e.g. SELECT * FROM {table} WHERE {col} IS NULL OR season IS NULL '
            f'OR season <> YEAR({col});'
        )


def _check_no_duplicates(bind) -> None:
    for table, group, label in (
        ('users_achievements', 'user_id, achievement_id, YEAR(`date`)', '(user, achievement, season)'),
        ('users_games', 'user_id, game_id, platform, YEAR(started_date)', '(user, game, platform, season)'),
    ):
        if bind.execute(sa.text(f'SELECT 1 FROM {table} GROUP BY {group} HAVING COUNT(*) > 1 LIMIT 1')).first():
            raise RuntimeError(f'{table}: several rows share the same {label}; merge them before migrating')


def upgrade() -> None:
    bind = op.get_bind()

    # 1. verify everything before changing anything (only while season is still a plain column)
    for table, (date_col, _) in TABLES.items():
        if _season_state(bind, table) == 'plain':
            _check_consistent(bind, table, date_col)
    _check_no_duplicates(bind)

    # 2. replace each plain column by a generated one
    for table, (date_col, expression) in TABLES.items():
        if _season_state(bind, table) == 'plain':
            for index in sa.inspect(bind).get_indexes(table):
                if index.get('unique') and 'season' in index['column_names']:
                    op.execute(f'ALTER TABLE {table} DROP INDEX `{index["name"]}`')
            op.execute(f'ALTER TABLE {table} DROP COLUMN season')
        if _season_state(bind, table) == 'missing':
            op.execute(f'ALTER TABLE {table} ADD COLUMN season INT GENERATED ALWAYS AS ({expression}) VIRTUAL')

    # the date decides the season, so it can never be missing
    op.execute('ALTER TABLE users_games MODIFY started_date DATE NOT NULL')
    op.execute('ALTER TABLE users_achievements MODIFY `date` DATE NOT NULL')

    # 3. keys: one entry per user/game/platform/season, one achievement per user and season
    if 'uq_users_games_entry' not in _index_names(bind, 'users_games'):
        op.execute('ALTER TABLE users_games ADD UNIQUE KEY uq_users_games_entry (user_id, game_id, platform, season)')
    names = _index_names(bind, 'users_achievements')
    if 'uq_users_achievements_season' not in names:
        op.execute(
            'ALTER TABLE users_achievements '
            'ADD UNIQUE KEY uq_users_achievements_season (user_id, achievement_id, season)'
        )
    # the old (user, achievement, date) key is implied by the one above
    for index in sa.inspect(bind).get_indexes('users_achievements'):
        if index.get('unique') and index['column_names'] == ['user_id', 'achievement_id', 'date']:
            op.execute(f'ALTER TABLE users_achievements DROP INDEX `{index["name"]}`')
    if 'ix_game_timers_user_season' not in _index_names(bind, 'game_timers'):
        op.execute('ALTER TABLE game_timers ADD INDEX ix_game_timers_user_season (user_id, season)')


def downgrade() -> None:
    bind = op.get_bind()
    for table, (date_col, expression) in TABLES.items():
        if _season_state(bind, table) == 'generated':
            op.execute(f'ALTER TABLE {table} MODIFY season INT NULL')
            op.execute(f'UPDATE {table} SET season = {expression}')
    if 'ix_game_timers_user_season' in _index_names(bind, 'game_timers'):
        op.execute('ALTER TABLE game_timers DROP INDEX ix_game_timers_user_season')
    if 'uq_users_achievements_season' in _index_names(bind, 'users_achievements'):
        op.execute('ALTER TABLE users_achievements DROP INDEX uq_users_achievements_season')
    op.execute('ALTER TABLE users_achievements ADD UNIQUE KEY user_id (user_id, achievement_id, `date`)')
    op.execute('ALTER TABLE users_games MODIFY started_date DATE NULL')
    op.execute('ALTER TABLE users_achievements MODIFY `date` DATE NULL')
