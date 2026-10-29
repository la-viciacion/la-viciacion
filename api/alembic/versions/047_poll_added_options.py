"""group_polls: option_keys and allow_adding_options

Revision ID: 047_poll_added_options
Revises: 046_group_polls
Create Date: 2026-10-29 12:00:00.000000

A poll can let the group add options of their own in Telegram. An option added there has no place in the list the app sent,
and the positions an answer carries shift as options come and go, so each option now has the id Telegram gives it for good
(`persistent_id`) and an answer is read by those ids.

  group_polls.option_keys            JSON list of those ids, in the same order as `options` (NULL for a poll launched
                                     before this: its answers are still read by position, as they always were)
  group_polls.allow_adding_options   the group may add options (default 0)

Purely additive: two new columns, nothing existing is rewritten or refused.

Re-runnable: each column is only added if it is missing. Downgrade drops both (the options added in the meantime stay in
`options`, but the poll goes back to being read by position, so an open poll should be closed first).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '047_poll_added_options'
down_revision: Union[str, None] = '046_group_polls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'group_polls'


def _columns() -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _columns()
    if 'option_keys' not in existing:
        op.add_column(TABLE, sa.Column('option_keys', sa.Text(), nullable=True))
    if 'allow_adding_options' not in existing:
        op.add_column(TABLE, sa.Column('allow_adding_options', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    existing = _columns()
    for column in ('allow_adding_options', 'option_keys'):
        if column in existing:
            op.drop_column(TABLE, column)
