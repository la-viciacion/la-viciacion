"""challenges and challenge_optouts: time-boxed goals chosen from predefined templates

Revision ID: 034_challenges
Revises: 033_achievement_review
Create Date: 2026-10-09 18:00:00.000000

A challenge is the definition of a goal made from a template written in code (see utils/challenges.py): who it is for,
its options and its period. Only the definition is stored; progress and completion are always derived from the sessions
and the library when asked.

  challenges        id, kind (the template), scope ('group' or 'user'), owner_user_id (the player a personal one is
                    for; NULL for the group's), created_by (who launched it; NULL if that account was deleted),
                    visibility ('public' for now), participation ('auto': every active player takes part and may opt
                    out; 'opt_in' is prepared and not used yet), title, params (the options, JSON text), game_id (the
                    game a challenge is about, if any: deleting the game deletes the challenge), starts_on, ends_on,
                    fingerprint (a hash of kind, options, period and owner: unique, so an equal challenge is refused),
                    total_notified_at (when the group was told its total was reached, so it is said once), created_at
  challenge_optouts challenge_id, user_id, created_at: who chose not to take part (primary key challenge_id + user_id)

Purely additive: two new tables, nothing existing is rewritten or refused (the only read is the collation of games.id,
so that the foreign key to it can be made).

Re-runnable: each table is only created if it is missing. Downgrade drops both (the challenges are lost; they are
definitions that an admin or a player made, with no copy anywhere else).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '034_challenges'
down_revision: Union[str, None] = '033_achievement_review'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHALLENGES = 'challenges'
OPTOUTS = 'challenge_optouts'


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _games_id_collation() -> str | None:
    """The collation of games.id: a foreign key needs both sides to have the same one, and a table created now
    would take the server's default, which the older tables may not share (see 016_foreign_keys)."""
    return op.get_bind().execute(sa.text(
        "SELECT collation_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'games' AND column_name = 'id'"
    )).scalar()


def upgrade() -> None:
    existing = _tables()
    if CHALLENGES not in existing:
        op.create_table(
            CHALLENGES,
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('kind', sa.String(32), nullable=False),
            sa.Column('scope', sa.String(8), nullable=False),
            sa.Column('owner_user_id', sa.Integer(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('visibility', sa.String(8), nullable=False, server_default='public'),
            sa.Column('participation', sa.String(8), nullable=False, server_default='auto'),
            sa.Column('title', sa.String(120), nullable=False),
            sa.Column('params', sa.Text(), nullable=False),
            sa.Column('game_id', sa.String(255, collation=_games_id_collation()), nullable=True),
            sa.Column('starts_on', sa.Date(), nullable=False),
            sa.Column('ends_on', sa.Date(), nullable=False),
            sa.Column('fingerprint', sa.String(64), nullable=False),
            sa.Column('total_notified_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_challenges_owner', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_challenges_creator', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['game_id'], ['games.id'], name='fk_challenges_game', ondelete='CASCADE'),
            sa.UniqueConstraint('fingerprint', name='uq_challenges_fingerprint'),
        )
    if OPTOUTS not in existing:
        op.create_table(
            OPTOUTS,
            sa.Column('challenge_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('challenge_id', 'user_id'),
            sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], name='fk_challenge_optouts_challenge', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_challenge_optouts_user', ondelete='CASCADE'),
        )


def downgrade() -> None:
    existing = _tables()
    for table in (OPTOUTS, CHALLENGES):  # the opt-outs point at the challenges
        if table in existing:
            op.drop_table(table)
