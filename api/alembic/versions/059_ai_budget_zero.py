"""AI budgets: 0 now means nothing of the group's key, and no cap (empty) means no limit

Revision ID: 059_ai_budget_zero
Revises: 058_ai_free_plan
Create Date: 2026-11-12 23:00:00.000000

Until now a monthly AI budget of 0 meant "no limit" (migration 057). It is confusing, and there was no way to give a player none of
the group's key: 0 now means exactly that, and an empty cap (no row in `app_settings`, NULL for a player) is what means no limit. The
values already stored with the old meaning are converted so that nobody's behaviour changes:

  app_settings   `ai.group_budget_month` and `ai.user_budget_month` stored as 0 (no limit) are deleted: no value is no limit.
  user_settings  `ai_group_budget_usd` = 0 (no limit for this player) becomes NULL (the default applies, which is no limit unless the
                 default is a cap) or, when the default `ai.user_budget_month` is a cap, 10000, the highest a cap can be, because
                 that player was the one exempt from it and no other value says so.

Nothing is refused. It converts what 0 meant, so it must run once: run again after an admin has set a 0 with the new meaning it
would turn that into "no limit", which is why a database at this revision is never taken back to the previous one and up again by
hand. Idempotent for the same state: with no 0 left it changes nothing.

Downgrade: the old code reads 0 as no limit, so a 0 with the new meaning (nothing of the group's key) is turned into 1, the nearest
the old code can say; "no limit" needs no change (no value was already no limit there, and 10000 stays a cap). What was 0 and
became 10000 stays 10000.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '059_ai_budget_zero'
down_revision: Union[str, None] = '058_ai_free_plan'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SETTINGS = 'app_settings'
USERS = 'user_settings'
COLUMN = 'ai_group_budget_usd'
KEYS = ('ai.group_budget_month', 'ai.user_budget_month')
USER_DEFAULT_KEY = 'ai.user_budget_month'
TOP = 10000


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_column() -> bool:
    return COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(USERS)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    default_cap = 0
    if SETTINGS in tables:
        found = bind.execute(sa.text(f"SELECT `value` FROM {SETTINGS} WHERE `key` = :key"), {'key': USER_DEFAULT_KEY}).scalar()
        default_cap = int(found) if found is not None and str(found).strip().lstrip('-').isdigit() else 0
    if USERS in tables and _has_column():
        # the players that were exempt from a cap that is a number: only 10000 says "as good as none"
        exempt = TOP if default_cap > 0 else None
        bind.execute(sa.text(f"UPDATE {USERS} SET {COLUMN} = :exempt WHERE {COLUMN} = 0"), {'exempt': exempt})
    if SETTINGS in tables:
        for key in KEYS:
            bind.execute(sa.text(f"DELETE FROM {SETTINGS} WHERE `key` = :key AND `value` = '0'"), {'key': key})


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables()
    if USERS in tables and _has_column():
        bind.execute(sa.text(f"UPDATE {USERS} SET {COLUMN} = 1 WHERE {COLUMN} = 0"))
    if SETTINGS in tables:
        for key in KEYS:
            bind.execute(sa.text(f"UPDATE {SETTINGS} SET `value` = '1' WHERE `key` = :key AND `value` = '0'"), {'key': key})
