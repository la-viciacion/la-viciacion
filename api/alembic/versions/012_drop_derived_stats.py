"""drop the stored statistics: users_statistics, games_statistics and users_games.played_time

Revision ID: 012_drop_derived_stats
Revises: 011_restore_old_library
Create Date: 2026-09-30 18:00:00.000000

Everything in these tables was a copy of something that can be computed from the
sessions (game_timers) at any moment, and every copy that drifts from its source is a
bug (empty game rankings, stale streaks, announcements swallowed). The application now
computes totals, rankings and streaks when they are asked for, and compares rankings
before/after a session instead of remembering the last announced position.

- users_statistics: total time, played days, streaks and the last announced ranking
  position of each user.
- games_statistics: total time and the last announced ranking position of each game.
- users_games.played_time: the time played in each library entry (now the sum of its
  sessions). completion_time, the time a game took to complete, is a recorded fact and stays.

DESTRUCTIVE but lossless in practice: the values are recomputed from game_timers on
every read; only the stored ranking positions (ephemeral) are gone. Take a backup first
anyway. Migrations 001-011 are untouched.

Re-runnable: every step checks what still exists. It refuses to run if users_games.played_time
takes part in an index together with other columns.

Downgrade recreates the two tables and the column empty; the previous version of the
application rebuilds their content on its next recompute.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '012_drop_derived_stats'
down_revision: Union[str, None] = '011_restore_old_library'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('users_statistics', 'games_statistics')


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _has_played_time(bind) -> bool:
    return 'played_time' in {c['name'] for c in sa.inspect(bind).get_columns('users_games')}


def _check_no_shared_indexes(bind) -> None:
    for index in sa.inspect(bind).get_indexes('users_games'):
        columns = set(index['column_names'])
        if 'played_time' in columns and columns != {'played_time'}:
            raise RuntimeError(
                f"users_games index {index['name']} mixes {sorted(columns)}; drop or redefine it by hand "
                'before running this migration'
            )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. verify before changing anything
    _check_no_shared_indexes(bind)

    # 2. column (its own single-column index goes first)
    if _has_played_time(bind):
        for index in sa.inspect(bind).get_indexes('users_games'):
            if index['column_names'] == ['played_time']:
                op.execute(f'ALTER TABLE users_games DROP INDEX `{index["name"]}`')
        op.execute('ALTER TABLE users_games DROP COLUMN played_time')

    # 3. tables
    for table in TABLES:
        if table in _tables(bind):
            op.execute(f'DROP TABLE {table}')


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_played_time(bind):
        op.execute('ALTER TABLE users_games ADD COLUMN played_time INT NULL AFTER score')
    tables = _tables(bind)
    if 'users_statistics' not in tables:
        op.create_table(
            'users_statistics',
            sa.Column('user_id', sa.Integer(), primary_key=True, autoincrement=False),
            sa.Column('played_time', sa.Integer()),
            sa.Column('current_ranking_hours', sa.Integer()),
            sa.Column('current_streak', sa.Integer()),
            sa.Column('best_streak', sa.Integer()),
            sa.Column('best_streak_date', sa.Date()),
            sa.Column('played_days', sa.Integer()),
            sa.Column('best_unplayed_streak', sa.Integer()),
            sa.Column('current_unplayed_streak', sa.Integer()),
            sa.Column('best_unplayed_streak_date', sa.Date()),
            sa.Column('played_games', sa.Integer()),
            sa.Column('completed_games', sa.Integer()),
        )
    if 'games_statistics' not in tables:
        op.create_table(
            'games_statistics',
            sa.Column('game_id', sa.String(255), primary_key=True),
            sa.Column('played_time', sa.Integer()),
            sa.Column('avg_time', sa.Integer()),
            sa.Column('current_ranking', sa.Integer()),
        )
