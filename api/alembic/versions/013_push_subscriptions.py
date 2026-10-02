"""push_subscriptions: the devices that receive Web Push notifications

Revision ID: 013_push_subscriptions
Revises: 012_drop_derived_stats
Create Date: 2026-09-30 20:00:00.000000

Adds the table that backs the installed-PWA notifications (utils/push.py). One row is
one browser/device of one user:

- endpoint: address of the browser's push service for that device (unique).
- p256dh, auth: the keys needed to encrypt the notice for that device.
- receive_group: whether the device also gets the notices that go to the Telegram
  group (the private ones, such as a forgotten timer, always arrive).

Purely additive: nothing existing is touched, so it is safe to run on any database.
Everything stays disabled until an admin generates the VAPID keys and enables
`push.enabled` in the panel.

Re-runnable: it checks whether the table already exists. Downgrade drops the table
(the devices have to subscribe again).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '013_push_subscriptions'
down_revision: Union[str, None] = '012_drop_derived_stats'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if 'push_subscriptions' in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(700), nullable=False),
        sa.Column('p256dh', sa.String(255), nullable=False),
        sa.Column('auth', sa.String(255), nullable=False),
        sa.Column('receive_group', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('endpoint', name='uq_push_subscriptions_endpoint'),
    )
    op.create_index('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id'])


def downgrade() -> None:
    bind = op.get_bind()
    if 'push_subscriptions' in sa.inspect(bind).get_table_names():
        op.drop_table('push_subscriptions')
