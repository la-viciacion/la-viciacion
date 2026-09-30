"""user_settings: personal preferences, one row per user

Revision ID: 014_user_settings
Revises: 013_push_subscriptions
Create Date: 2026-09-30 21:00:00.000000

Adds the table that holds what each user can tune from their profile. One row per
user, one typed column per setting; a NULL column means "use the default", so a user
without a row (everybody, right after this migration) behaves exactly as before.
The first setting is `forgotten_timer_hours` (how long a timer may run before the
reminder; the default lives in code). New settings are later `ADD COLUMN ... NULL`.

- user_id: primary key and foreign key to users.id, deleted along with the user.
- forgotten_timer_hours: whole hours, 1-24 (CHECK enforces it; MariaDB validates
  CHECK constraints on insert/update only).

Purely additive: nothing existing is touched, so it is safe to run on any database.

Re-runnable: it checks whether the table already exists. Downgrade drops the table
(the preferences are lost and revert to the defaults).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '014_user_settings'
down_revision: Union[str, None] = '013_push_subscriptions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if 'user_settings' in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('forgotten_timer_hours', sa.SmallInteger(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_settings_user', ondelete='CASCADE'),
        sa.CheckConstraint(
            'forgotten_timer_hours IS NULL OR forgotten_timer_hours BETWEEN 1 AND 24',
            name='ck_user_settings_forgotten_hours',
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if 'user_settings' in sa.inspect(bind).get_table_names():
        op.drop_table('user_settings')
