"""achievements.description: how an achievement is earned, written for the player

Revision ID: 062_ach_description
Revises: 061_user_ai_keys
Create Date: 2026-11-14 20:00:00.000000

The achievements page used to show the announcement (`message`, the text sent to Telegram, with the player and the game taken out) as
the description of an achievement. What a player needs there is how to earn it, so each achievement gets its own text. One addition:

  achievements.description   VARCHAR(255), nullable. It is left empty here: the code fills it at start-up for every row that has none
                             (crud/achievements.py), from the definitions in utils/achievements.py, and never overwrites one an admin edited.

No data is read or changed. The step is only done if the column is missing, so it can be run again.

Downgrade drops the column: the descriptions are lost, and the code fills them again if the migration is run once more.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '062_ach_description'
down_revision: Union[str, None] = '061_user_ai_keys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'achievements'
COLUMN = 'description'


def _columns() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if COLUMN not in _columns():
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=255), nullable=True))


def downgrade() -> None:
    if COLUMN in _columns():
        op.drop_column(TABLE, COLUMN)
