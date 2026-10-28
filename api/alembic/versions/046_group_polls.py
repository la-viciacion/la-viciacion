"""group_polls and group_poll_votes: the polls an admin launches into the Telegram group

Revision ID: 046_group_polls
Revises: 045_game_prices
Create Date: 2026-10-28 20:00:00.000000

An admin can launch a poll (a question and 2 to 10 options) into the Telegram group from the panel. It is a native,
**non-anonymous** Telegram poll sent by the app's bot, so who voted what is known: the bot hears each answer and tells
the API, which keeps it here. The poll is closed by hand or when its deadline passes.

  group_polls       id, question, options (JSON list of texts, in the order Telegram shows them), multiple (several
                    answers allowed), telegram_poll_id (what an answer names; unique), telegram_message_id (what
                    closing it in Telegram needs), closes_at (the deadline; NULL = only by hand), closed_at (NULL =
                    open; once set, no answer counts), closed_by (the admin; NULL if the deadline closed it or the
                    account is gone), telegram_stopped (Telegram has been told to stop it; a failure there does not
                    keep it open here, it is tried again), telegram_voters (how many voters Telegram counted when it
                    was stopped, to notice answers this table missed), created_by, created_at
  group_poll_votes  poll_id, telegram_user_id, option_ids (JSON list of the option positions that person chose now;
                    the key is one row per person and poll), updated_at. Which account a Telegram id is, is derived
                    from `users.telegram_id` when asked, never stored: a voter with no account is just an id.

The tally, the winner and who voted what are derived from these rows when asked.

Purely additive: two new tables, nothing existing is rewritten or refused.

Re-runnable: each table is only created if it is missing. Downgrade drops both (the polls and their votes are lost;
the polls stay in the Telegram group).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '046_group_polls'
down_revision: Union[str, None] = '045_game_prices'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLLS = 'group_polls'
VOTES = 'group_poll_votes'


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if POLLS not in existing:
        op.create_table(
            POLLS,
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('question', sa.String(300), nullable=False),
            sa.Column('options', sa.Text(), nullable=False),
            sa.Column('multiple', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('telegram_poll_id', sa.String(32), nullable=False),
            sa.Column('telegram_message_id', sa.BigInteger(), nullable=False),
            sa.Column('closes_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('closed_by', sa.Integer(), nullable=True),
            sa.Column('telegram_stopped', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('telegram_voters', sa.Integer(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['closed_by'], ['users.id'], name='fk_group_polls_closer', ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_group_polls_creator', ondelete='SET NULL'),
            sa.UniqueConstraint('telegram_poll_id', name='uq_group_polls_telegram'),
        )
    if VOTES not in existing:
        op.create_table(
            VOTES,
            sa.Column('poll_id', sa.Integer(), primary_key=True, autoincrement=False),
            sa.Column('telegram_user_id', sa.BigInteger(), primary_key=True, autoincrement=False),
            sa.Column('option_ids', sa.Text(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['poll_id'], [POLLS + '.id'], name='fk_group_poll_votes_poll', ondelete='CASCADE'),
        )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in (VOTES, POLLS):
        if table in existing:
            op.drop_table(table)
