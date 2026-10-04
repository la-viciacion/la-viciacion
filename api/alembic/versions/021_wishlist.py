"""users_wishlist: the games a player wants to play, including the ones still to be released

Revision ID: 021_wishlist
Revises: 020_show_playing
Create Date: 2026-10-04 12:00:00.000000

A player keeps a list of the games they want to play. Only the wish is stored:

  users_wishlist   id, user_id -> users, game_id -> games, added_at DATETIME
                   unique (user_id, game_id)

Whether a game is still to be released, whether the wish is pending (the game is not in the player's
library yet) and who else wants it are derived from `games.release_date` and `users_games` when asked.

Purely additive: a new table, nothing existing is read, rewritten or refused. Both keys are RESTRICT,
like the other user/game tables (016): the admin panel removes a user's or a game's wishes before
deleting them.

The table is created with the type of `users.id` and the character set and collation of `games.id`
(read from information_schema), because a foreign key needs both sides to match.

Re-runnable: the table is only created if it is missing.

Downgrade: drops `users_wishlist` (the wishes are lost).
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '021_wishlist'
down_revision: Union[str, None] = '020_show_playing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users_wishlist'
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


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind):
        return
    user_type, _, _ = _column_info(bind, 'users', 'id')
    game_type, charset, collation = _column_info(bind, 'games', 'id')
    op.execute(
        f'CREATE TABLE `{TABLE}` ('
        f'`id` INT NOT NULL AUTO_INCREMENT, '
        f'`user_id` {user_type} NOT NULL, '
        f'`game_id` {game_type} CHARACTER SET {charset} COLLATE {collation} NOT NULL, '
        f'`added_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, '
        f'PRIMARY KEY (`id`), '
        f'CONSTRAINT `uq_users_wishlist_user_game` UNIQUE (`user_id`, `game_id`), '
        f'CONSTRAINT `fk_users_wishlist_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`), '
        f'CONSTRAINT `fk_users_wishlist_game` FOREIGN KEY (`game_id`) REFERENCES `games` (`id`)'
        f') ENGINE=InnoDB DEFAULT CHARSET={charset} COLLATE={collation}'
    )


def downgrade() -> None:
    if _has_table(op.get_bind()):
        op.drop_table(TABLE)
