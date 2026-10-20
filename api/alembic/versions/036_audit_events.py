"""audit_log: security events (logins, password changes) with the caller's address

Revision ID: 036_audit_events
Revises: 035_secrets_env_only
Create Date: 2026-10-20 12:00:00.000000

The audit log (migration 022) only held the admin panel's writes. It now also keeps what the players do
that matters for security (logins, failed logins, password changes and recoveries, changes of their own
email or Telegram id, a refused access to the panel), in the same table so there is one place to look.
Three nullable columns are added:

- `event`: what happened, for the rows that are not a panel write ("login", "login_failed",
  "password_changed"...). NULL on every existing row and on panel writes. Indexed to filter by it.
- `ip`: the address the request came from, as the server sees it (45 characters fit an IPv6 one).
- `user_agent`: the client's `User-Agent`, cut to 255 characters.

Additive only: nothing existing is read or rewritten, old rows keep NULL in the three columns.

Re-runnable: each column and the index are only created if missing.

Downgrade: drops the index and the three columns (the events and the addresses are lost; the rows stay,
so the events would then read as panel writes with no detail).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '036_audit_events'
down_revision: Union[str, None] = '035_secrets_env_only'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'audit_log'
INDEX = 'ix_audit_log_event'
COLUMNS = (
    ('event', sa.String(length=40)),
    ('ip', sa.String(length=45)),
    ('user_agent', sa.String(length=255)),
)


def upgrade() -> None:
    bind = op.get_bind()
    present = {column['name'] for column in sa.inspect(bind).get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in present:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    if INDEX not in {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, ['event'])


def downgrade() -> None:
    bind = op.get_bind()
    if INDEX in {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}:
        op.drop_index(INDEX, table_name=TABLE)
    present = {column['name'] for column in sa.inspect(bind).get_columns(TABLE)}
    for name, _ in reversed(COLUMNS):
        if name in present:
            op.drop_column(TABLE, name)
