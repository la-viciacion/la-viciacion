"""drop the Clockify leftovers: users.clockify_id/clockify_key and the request_sync, logs and other_tags tables

Revision ID: 010_drop_clockify
Revises: 009_settings_jobs
Create Date: 2026-09-29 20:00:00.000000

Clockify is gone for good and nothing reads or writes these any more:

- users.clockify_id / users.clockify_key: per-user Clockify credentials.
- request_sync: bookkeeping of processed Clockify webhook requests.
- logs: old action log, no code path uses it.
- other_tags: Clockify tag catalogue (only the "Completed" tag was ever read).

`platform_tags` is NOT dropped: it is the platform catalogue that
users_games.platform and game_timers.platform still refer to.

DESTRUCTIVE: the columns and tables are dropped together with their content
(explicit decision: they were only kept "for history"). Take a backup first.
Migrations 001-009 are untouched: they still read the legacy schema while
importing an old (v1) backup, which is why this one comes last.

Re-runnable: every step checks what still exists. It refuses to run if a
column takes part in an index together with other columns (dropping it would
silently change that index); single-column indexes on them go with the column.

Downgrade: recreates the two columns (NULL) and the three tables empty. The
dropped content cannot be restored; restore the backup for that.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '010_drop_clockify'
down_revision: Union[str, None] = '009_settings_jobs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USER_COLUMNS = ('clockify_id', 'clockify_key')
TABLES = ('request_sync', 'logs', 'other_tags')


def _user_columns(bind) -> set:
    return {c['name'] for c in sa.inspect(bind).get_columns('users')}


def _tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def _check_no_shared_indexes(bind) -> None:
    for index in sa.inspect(bind).get_indexes('users'):
        columns = set(index['column_names'])
        if columns & set(USER_COLUMNS) and not columns <= set(USER_COLUMNS):
            raise RuntimeError(
                f"users index {index['name']} mixes {sorted(columns)}; drop or redefine it by hand "
                'before running this migration'
            )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. verify before changing anything
    _check_no_shared_indexes(bind)

    # 2. columns (their own single-column indexes go first)
    for column in USER_COLUMNS:
        if column in _user_columns(bind):
            for index in sa.inspect(bind).get_indexes('users'):
                if index['column_names'] == [column]:
                    op.execute(f'ALTER TABLE users DROP INDEX `{index["name"]}`')
            op.execute(f'ALTER TABLE users DROP COLUMN {column}')

    # 3. tables
    for table in TABLES:
        if table in _tables(bind):
            op.execute(f'DROP TABLE {table}')


def downgrade() -> None:
    bind = op.get_bind()
    for column in USER_COLUMNS:
        if column not in _user_columns(bind):
            op.execute(f'ALTER TABLE users ADD COLUMN {column} VARCHAR(255) NULL')
    tables = _tables(bind)
    if 'request_sync' not in tables:
        op.create_table(
            'request_sync',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('request_id', sa.String(255), primary_key=True),
        )
    if 'logs' not in tables:
        op.create_table(
            'logs',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('player', sa.String(255)),
            sa.Column('action', sa.String(255)),
            sa.Column('date', sa.DateTime()),
        )
    if 'other_tags' not in tables:
        op.create_table(
            'other_tags',
            sa.Column('id', sa.String(255), primary_key=True),
            sa.Column('name', sa.String(255)),
        )
