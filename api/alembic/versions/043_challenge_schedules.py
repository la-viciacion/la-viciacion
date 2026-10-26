"""challenge_schedules: group challenges that launch themselves every month

Revision ID: 043_challenge_schedules
Revises: 042_challenge_proposals
Create Date: 2026-10-26 14:00:00.000000

An admin can define a group challenge that is launched by itself at the start of every month: a themed one with fixed
options, or a game of the month whose game rotates along a list. Only the definition is stored; which game it is
each month is worked out from `first_month` and the position of the month (never stored), and the challenge it
launches is a row of `challenges` like any other (an equal one is refused by the fingerprint, so a month is never
launched twice).

  challenge_schedules  id, label (what the admin calls it), kind (the template), options (the template's options
                       without the month and the game, JSON text), games (the list of game ids a game of the month
                       rotates along, JSON text; NULL for the others), participation ('auto' or 'opt_in', as in
                       `challenges`), announce (tell the group when it launches; off by default), active,
                       first_month (the first day of the first month it launches for), last_month (the first day of
                       the last month it was launched for: what keeps it from running twice for a month),
                       last_status (what the last run said, e.g. why it could not launch), created_by (the admin;
                       NULL if that account was deleted: the challenges are launched without a creator then),
                       created_at

Purely additive: one new table, nothing existing is rewritten or refused.

Re-runnable: the table is only created if it is missing. Downgrade drops it (the definitions are lost; the
challenges they launched stay).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '043_challenge_schedules'
down_revision: Union[str, None] = '042_challenge_proposals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'challenge_schedules'


def upgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('options', sa.Text(), nullable=False),
        sa.Column('games', sa.Text(), nullable=True),
        sa.Column('participation', sa.String(8), nullable=False, server_default='auto'),
        sa.Column('announce', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('first_month', sa.Date(), nullable=False),
        sa.Column('last_month', sa.Date(), nullable=True),
        sa.Column('last_status', sa.String(255), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_challenge_schedules_creator', ondelete='SET NULL'),
    )


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
