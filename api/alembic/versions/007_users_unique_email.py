"""normalize user emails and make them unique

Revision ID: 007_users_unique_email
Revises: 006_backfill_timer_platform
Create Date: 2026-09-29 16:30:00.000000

The email is now the login identifier, so it must identify one account.
Emails are trimmed and lower-cased (blank ones become NULL, which a unique
index allows many of), then a UNIQUE index is added. The migration refuses to
run, listing the offending addresses, if two accounts share one: those have to
be resolved by hand first (the unique index would fail anyway).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '007_users_unique_email'
down_revision: Union[str, None] = '006_backfill_timer_platform'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_users_email'


def _has_unique_email(bind) -> bool:
    inspector = sa.inspect(bind)
    for index in inspector.get_indexes('users'):
        if index.get('unique') and index['column_names'] == ['email']:
            return True
    return any(c['column_names'] == ['email'] for c in inspector.get_unique_constraints('users'))


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("UPDATE users SET email = NULLIF(LOWER(TRIM(email)), '') WHERE email IS NOT NULL")

    duplicates = bind.execute(
        sa.text("SELECT email, COUNT(*) AS n FROM users WHERE email IS NOT NULL GROUP BY email HAVING n > 1")
    ).fetchall()
    if duplicates:
        listing = ', '.join(f'{row[0]} ({row[1]} accounts)' for row in duplicates)
        raise RuntimeError(f'Cannot make users.email unique, duplicated emails: {listing}')

    if not _has_unique_email(bind):
        op.create_unique_constraint(INDEX, 'users', ['email'])


def downgrade() -> None:
    if _has_unique_email(op.get_bind()):
        op.drop_constraint(INDEX, 'users', type_='unique')
