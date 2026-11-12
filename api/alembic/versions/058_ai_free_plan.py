"""ai_usage: whether the key that paid a call was on a free plan, so its real cost was nothing

Revision ID: 058_ai_free_plan
Revises: 057_ai_budget
Create Date: 2026-11-12 22:00:00.000000

Some provider keys of the group are on a free plan (Google's, for now): what they answer is estimated at the price list like
any call, and that estimate is worth keeping, but nothing is charged for it. An admin says which providers are on a free plan
(settings `ai.free_plan.<provider>`), and each call records, when it is made, whether the group's key that paid it was one of those.
It has to be a fact of the call and not read from the setting later: a key can move to a paid plan, and the calls made before must
keep what they were. One new column on the record of calls:

  free_plan   1 when the key of the group that paid the call was on a free plan: its real cost is 0 whatever `cost_micros`
              (the estimate, kept) says. 0 otherwise, and always 0 for a player's own key.

NOT NULL with a default of 0: every row that exists keeps counting at its estimate (nothing is rewritten, read or refused). The
calls already recorded cannot be told apart afterwards, so those made on a free key before this migration stay counted as if they had
been paid.

Re-runnable: the column is only added if it is missing.

Downgrade drops the column: which calls were on a free plan is lost, and every call counts at its estimate again.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '058_ai_free_plan'
down_revision: Union[str, None] = '057_ai_budget'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'ai_usage'
COLUMN = 'free_plan'


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _existing():
        op.add_column(TABLE, sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    if COLUMN in _existing():
        op.drop_column(TABLE, COLUMN)
