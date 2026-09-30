"""foreign keys: the database enforces the relations the app used to keep by hand

Revision ID: 016_foreign_keys
Revises: 015_seed_platforms
Create Date: 2026-09-30 19:00:00.000000

Until now no table pointed at another one: a session could name a game that does not
exist, deleting a user left devices behind, and every delete cascaded by code in
`routers/manage.py`. This adds the missing foreign keys:

  game_timers        user_id -> users, game_id -> games, platform -> platform_tags
  users_games        user_id -> users, game_id -> games, platform -> platform_tags
  users_achievements user_id -> users, achievement_id -> achievements, game_id -> games
  push_subscriptions user_id -> users        (ON DELETE CASCADE: a device belongs to its user)
  app_settings       updated_by -> users     (ON DELETE SET NULL: only says who edited it)

Everything else is RESTRICT (MariaDB's default): a user or a game with sessions, library
entries or achievements cannot be deleted until those are gone, which is what the admin
panel already does (it asks for confirmation and removes them first). NULL stays allowed
where the column is nullable (a session without a platform, an achievement without a
game). `user_settings` already had its key (014).

Refuses to run on data that breaks a key. First phase, read-only: every reference is
checked and, if some row points at something that does not exist (or an empty string where
an id is expected), the migration aborts with the table, the column, how many rows and
some of the offending values, and touches nothing. Fixing them is a human decision: point
them at the right row, or delete them, and run it again. It also aborts if a column that
must match its target in type does not.

Second phase: `game_timers.platform` (created by 002 with the server's default collation)
is converted to `utf8mb4_general_ci` when it differs from `platform_tags.id`, because a
key needs both sides to have the same collation. That is a lossless conversion of a
column that is in no unique key. Third: the keys are added, each only if missing.

Re-runnable: every step checks what is already there. Adding a key builds an index on the
column if there is none, which on these table sizes is instantaneous.

Downgrade: drops these keys (and only them). The collation change is not undone: it is
harmless and the previous value depended on the server.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016_foreign_keys'
down_revision: Union[str, None] = '015_seed_platforms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, table, column, referenced table, referenced column, ON DELETE clause or None)
KEYS = [
    ('fk_game_timers_user', 'game_timers', 'user_id', 'users', 'id', None),
    ('fk_game_timers_game', 'game_timers', 'game_id', 'games', 'id', None),
    ('fk_game_timers_platform', 'game_timers', 'platform', 'platform_tags', 'id', None),
    ('fk_users_games_user', 'users_games', 'user_id', 'users', 'id', None),
    ('fk_users_games_game', 'users_games', 'game_id', 'games', 'id', None),
    ('fk_users_games_platform', 'users_games', 'platform', 'platform_tags', 'id', None),
    ('fk_users_achievements_user', 'users_achievements', 'user_id', 'users', 'id', None),
    ('fk_users_achievements_ach', 'users_achievements', 'achievement_id', 'achievements', 'id', None),
    ('fk_users_achievements_game', 'users_achievements', 'game_id', 'games', 'id', None),
    ('fk_push_subscriptions_user', 'push_subscriptions', 'user_id', 'users', 'id', 'CASCADE'),
    ('fk_app_settings_updated_by', 'app_settings', 'updated_by', 'users', 'id', 'SET NULL'),
]
SAMPLE = 5


def _column(bind, table: str, column: str) -> dict:
    row = bind.execute(
        sa.text(
            'SELECT column_type, collation_name FROM information_schema.columns '
            'WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c'
        ),
        {'t': table, 'c': column},
    ).one()
    return {'type': row[0], 'collation': row[1]}


def _existing_keys(bind, table: str) -> set:
    return {fk['name'] for fk in sa.inspect(bind).get_foreign_keys(table)}


def _orphans(bind, table, column, ref_table, ref_column, collation) -> tuple:
    """(how many rows point at nothing, some of the values). Identifiers come from KEYS."""
    # compared with the target's collation: the two sides may still differ before phase two
    on = f'child.`{column}` = parent.`{ref_column}`'
    if collation:
        on = f'child.`{column}` COLLATE {collation} = parent.`{ref_column}` COLLATE {collation}'
    missing = f'FROM `{table}` child LEFT JOIN `{ref_table}` parent ON {on} ' \
              f'WHERE child.`{column}` IS NOT NULL AND parent.`{ref_column}` IS NULL'
    count = bind.execute(sa.text(f'SELECT COUNT(*) {missing}')).scalar()
    values = [
        row[0]
        for row in bind.execute(sa.text(f'SELECT DISTINCT child.`{column}` {missing} LIMIT {SAMPLE}')).fetchall()
    ] if count else []
    return count, values


def _check(bind) -> None:
    problems = []
    for name, table, column, ref_table, ref_column, _ in KEYS:
        if name in _existing_keys(bind, table):
            continue
        child, parent = _column(bind, table, column), _column(bind, ref_table, ref_column)
        if child['type'] != parent['type']:
            problems.append(f'{table}.{column} is {child["type"]} but {ref_table}.{ref_column} is {parent["type"]}: '
                            f'a foreign key needs the same type')
            continue
        count, values = _orphans(bind, table, column, ref_table, ref_column, parent['collation'])
        if count:
            problems.append(
                f'{table}.{column}: {count} row(s) point at a {ref_table}.{ref_column} that does not exist, '
                f'e.g. {values!r}. List them with: SELECT child.* FROM {table} child LEFT JOIN {ref_table} parent '
                f'ON child.{column} = parent.{ref_column} WHERE child.{column} IS NOT NULL AND parent.{ref_column} IS NULL'
            )
        if child['collation'] != parent['collation']:
            unique = [i for i in sa.inspect(bind).get_indexes(table) if i.get('unique') and column in i['column_names']]
            if unique:
                problems.append(f'{table}.{column} needs its collation changed to match {ref_table}.{ref_column} '
                                f'but is part of the unique key {unique[0]["name"]}')
    if problems:
        raise RuntimeError(
            'Cannot add the foreign keys, nothing was changed. Fix the data (point those rows at the right '
            'record, or delete them) and start again:\n- ' + '\n- '.join(problems)
        )


def _align_collations(bind) -> None:
    for name, table, column, ref_table, ref_column, _ in KEYS:
        if name in _existing_keys(bind, table):
            continue
        child, parent = _column(bind, table, column), _column(bind, ref_table, ref_column)
        if child['collation'] and child['collation'] != parent['collation']:
            nullable = bind.execute(
                sa.text('SELECT is_nullable FROM information_schema.columns WHERE table_schema = DATABASE() '
                        'AND table_name = :t AND column_name = :c'),
                {'t': table, 'c': column},
            ).scalar()
            op.execute(
                f'ALTER TABLE `{table}` MODIFY `{column}` {child["type"]} COLLATE {parent["collation"]} '
                f'{"NULL" if nullable == "YES" else "NOT NULL"}'
            )


def upgrade() -> None:
    bind = op.get_bind()
    _check(bind)
    _align_collations(bind)
    for name, table, column, ref_table, ref_column, on_delete in KEYS:
        if name not in _existing_keys(bind, table):
            clause = f' ON DELETE {on_delete}' if on_delete else ''
            op.execute(
                f'ALTER TABLE `{table}` ADD CONSTRAINT `{name}` FOREIGN KEY (`{column}`) '
                f'REFERENCES `{ref_table}` (`{ref_column}`){clause}'
            )


def downgrade() -> None:
    bind = op.get_bind()
    for name, table, *_ in KEYS:
        if name in _existing_keys(bind, table):
            op.execute(f'ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`')
