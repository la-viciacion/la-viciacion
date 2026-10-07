"""user_settings.place_* and birth_date: where a player lives and when they were born

Revision ID: 030_user_place_birth
Revises: 029_achievement_levels
Create Date: 2026-10-07 22:00:00.000000

Two new personal data, both optional, for the achievements that depend on something outside the app:

  place_name, place_latitude, place_longitude   the city a player chose from a geocoder's answer (never a GPS fix),
                                                 so that the weather of a day can be asked for. The coordinates are
                                                 those of the city's centre, with five decimals.
  birth_date                                      for the birthday achievement.

Purely additive: four nullable columns on a table whose rows are all NULL for them, which means "not set". Nothing
is rewritten or refused. Without a place there are no weather achievements, without a birth date no birthday.

Re-runnable: each column is only added if it is missing. Downgrade drops them (the places and birth dates are lost).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '030_user_place_birth'
down_revision: Union[str, None] = '029_achievement_levels'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = (
    ('place_name', sa.String(255)),
    ('place_latitude', sa.Numeric(8, 5)),
    ('place_longitude', sa.Numeric(8, 5)),
    ('birth_date', sa.Date()),
)


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _existing()
    for name, kind in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    existing = _existing()
    for name, _ in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
