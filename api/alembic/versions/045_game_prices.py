"""users_game_prices: what a player paid for a game, per platform

Revision ID: 045_game_prices
Revises: 044_challenge_notice_channels
Create Date: 2026-10-27 12:00:00.000000

A player can note the price of a game they own, once for each platform they have it on (a game bought on PC and on
Switch is two purchases). The app derives from it the cost per hour of a game (the price over the hours played) and, for
the group, a mean cost per hour that is only shown when at least three players contribute to it (so nobody's price can be
worked out); the price of a player is only theirs to read (and an administrator's, like the rest of their data).

  users_game_prices  id, user_id (deleting the player deletes their prices), game_id (deleting the game deletes them),
                     platform (one of platform_tags: a platform that has prices cannot be deleted, like one that has
                     entries), amount_cents (the price in euro cents, 0 for a free game), updated_at. One price for each
                     player, game and platform

It is not stored in `users_games` because that table has a row for each platform *and season* (the price would be repeated
in every season and lost with an entry that an admin deletes) and only has a row once the game was played.

Purely additive: one new table, nothing existing is rewritten or refused (the only reads are the collations of games.id and
platform_tags.id, so that their foreign keys can be made).

Re-runnable: the table is only created if it is missing. Downgrade drops it (the prices are lost: they are data the
players typed, with no copy anywhere else).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '045_game_prices'
down_revision: Union[str, None] = '044_challenge_notice_channels'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'users_game_prices'


def _collation(table: str) -> str | None:
    """The collation of `table`.id: a foreign key needs both sides to have the same one, and a table created now would take
    the server's default, which the older tables may not share (see 016_foreign_keys)."""
    return op.get_bind().execute(
        sa.text(
            "SELECT collation_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :table AND column_name = 'id'"
        ),
        {'table': table},
    ).scalar()


def upgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.String(255, collation=_collation('games')), nullable=False),
        sa.Column('platform', sa.String(255, collation=_collation('platform_tags')), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_game_prices_user', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], name='fk_game_prices_game', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['platform'], ['platform_tags.id'], name='fk_game_prices_platform'),
        sa.UniqueConstraint('user_id', 'game_id', 'platform', name='uq_game_prices_purchase'),
    )


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
