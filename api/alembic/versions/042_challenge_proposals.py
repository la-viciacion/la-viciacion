"""challenge_proposals: the group challenges that players propose and an admin approves or rejects

Revision ID: 042_challenge_proposals
Revises: 041_wishlist_release_channels
Create Date: 2026-10-26 13:00:00.000000

A player can propose a challenge for the whole group (a game of the month or a themed one, see utils/challenges.py);
an admin approves it, which launches it like any other group challenge, or rejects it with a note. Only the proposal
is stored here: the challenge it becomes is a row of `challenges`, whose progress is derived as always.

  challenge_proposals  id, proposer_id (the player; deleting the account deletes their proposals), kind (the
                       template), options (what the player chose, JSON text), title (as the challenge would be
                       called, for the lists), fingerprint (the hash of the challenge it would be, so an equal
                       pending proposal is refused), status ('pending', 'approved' or 'rejected'), decision_note
                       (why it was rejected, optional), decided_by (the admin; NULL if that account was deleted),
                       decided_at, challenge_id (the challenge an approval launched; NULL if it was deleted since),
                       created_at

Purely additive: one new table, nothing existing is rewritten or refused.

Re-runnable: the table is only created if it is missing. Downgrade drops it (the proposals are lost; the challenges
they became stay, as they are rows of their own).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '042_challenge_proposals'
down_revision: Union[str, None] = '041_wishlist_release_channels'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'challenge_proposals'


def upgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('proposer_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('options', sa.Text(), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('status', sa.String(8), nullable=False, server_default='pending'),
        sa.Column('decision_note', sa.String(255), nullable=True),
        sa.Column('decided_by', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('challenge_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['proposer_id'], ['users.id'], name='fk_challenge_proposals_proposer', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['decided_by'], ['users.id'], name='fk_challenge_proposals_decider', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], name='fk_challenge_proposals_challenge', ondelete='SET NULL'),
    )


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
