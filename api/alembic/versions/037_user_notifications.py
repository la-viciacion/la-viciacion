"""user_notifications: the players' notification inbox

Revision ID: 037_user_notifications
Revises: 036_audit_events
Create Date: 2026-10-20 18:00:00.000000

A player who missed a push (or has them off) can read what the group and they were told in the app. Each
notice is stored once per recipient, so a player deletes theirs without touching anyone else's; the
scheduler purges the old ones (setting `inbox.retention_days`, 14 by default). Notices are events, not
something derivable, so unlike totals and rankings they have to be stored.

Creates the table `user_notifications` (id, user_id -> users ON DELETE CASCADE, title, body, url,
created_at, read_at) and an index on (user_id, created_at). Additive only: nothing existing is read or
rewritten.

Re-runnable: the table and the index are only created if missing.

Downgrade: drops the table (the stored notices are lost; they are a copy of what was already sent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037_user_notifications'
down_revision: Union[str, None] = '036_audit_events'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_notifications'
INDEX = 'ix_user_notifications_user_created'


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            TABLE,
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=80), nullable=False),
            sa.Column('body', sa.String(length=255), server_default=sa.text("''"), nullable=False),
            sa.Column('url', sa.String(length=200), server_default=sa.text("'/'"), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_notifications_user', ondelete='CASCADE'),
        )
    if INDEX not in {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}:
        op.create_index(INDEX, TABLE, ['user_id', 'created_at'])


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
