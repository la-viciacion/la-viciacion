"""game_scores: one rating (1-100) per user and game; users_games.score is dropped

Revision ID: 019_game_scores
Revises: 018_timer_notice_minutes
Create Date: 2026-10-03 18:00:00.000000

A player rates a game once, whatever the number of seasons or platforms they played it on, so
the rating cannot live in `users_games` (one row per user, game, platform and season). It goes in
a table of its own:

  game_scores   id, user_id -> users, game_id -> games, score SMALLINT 1-100, updated_at
                unique (user_id, game_id); the CHECK refuses anything outside 1-100
                (MariaDB validates CHECK constraints on insert/update only)

Both keys are RESTRICT, like the other user/game tables (016): the admin panel removes a user's or
a game's ratings before deleting them.

DESTRUCTIVE, decided by the owner of the data: `users_games.score` (a float 0-10 that only the
admin panel ever wrote, and that the app never read) is DROPPED WITHOUT COPYING ITS VALUES into the
new table. Ratings start from zero. Take a backup first (docs/deployment.md#backups-and-restore);
the downgrade can only bring the column back empty.

The table is created with the type of `users.id` and the character set and collation of `games.id`
(read from information_schema), because a foreign key needs both sides to match.

Re-runnable: each step first checks whether it is already done.

Downgrade: drops `game_scores` (the ratings are lost) and adds `users_games.score` back as an empty
FLOAT NULL after `completed_date`, where it was.
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '019_game_scores'
down_revision: Union[str, None] = '018_timer_notice_minutes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'game_scores'
OLD_TABLE = 'users_games'
OLD_COLUMN = 'score'
SAFE = re.compile(r'^[A-Za-z0-9_(), ]+$')  # what information_schema returns for a type or a collation


def _column_info(bind, table: str, column: str) -> tuple:
    row = bind.execute(
        sa.text(
            'SELECT column_type, character_set_name, collation_name FROM information_schema.columns '
            'WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c'
        ),
        {'t': table, 'c': column},
    ).one()
    for value in row:
        if value is not None and not SAFE.match(value):
            raise RuntimeError(f'Unexpected column description for {table}.{column}: {value!r}')
    return row


def _has_table(bind) -> bool:
    return TABLE in sa.inspect(bind).get_table_names()


def _has_old_column(bind) -> bool:
    return OLD_COLUMN in {c['name'] for c in sa.inspect(bind).get_columns(OLD_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        user_type, _, _ = _column_info(bind, 'users', 'id')
        game_type, charset, collation = _column_info(bind, 'games', 'id')
        op.execute(
            f'CREATE TABLE `{TABLE}` ('
            f'`id` INT NOT NULL AUTO_INCREMENT, '
            f'`user_id` {user_type} NOT NULL, '
            f'`game_id` {game_type} CHARACTER SET {charset} COLLATE {collation} NOT NULL, '
            f'`score` SMALLINT NOT NULL, '
            f'`updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, '
            f'PRIMARY KEY (`id`), '
            f'CONSTRAINT `uq_game_scores_user_game` UNIQUE (`user_id`, `game_id`), '
            f'CONSTRAINT `ck_game_scores_range` CHECK (`score` BETWEEN 1 AND 100), '
            f'CONSTRAINT `fk_game_scores_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`), '
            f'CONSTRAINT `fk_game_scores_game` FOREIGN KEY (`game_id`) REFERENCES `games` (`id`)'
            f') ENGINE=InnoDB DEFAULT CHARSET={charset} COLLATE={collation}'
        )
    if _has_old_column(bind):
        op.drop_column(OLD_TABLE, OLD_COLUMN)


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_old_column(bind):
        op.execute(f'ALTER TABLE `{OLD_TABLE}` ADD COLUMN `{OLD_COLUMN}` FLOAT NULL AFTER `completed_date`')
    if _has_table(bind):
        op.drop_table(TABLE)
