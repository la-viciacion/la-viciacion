"""app settings, scheduled job state and unique Telegram ids

Revision ID: 009_settings_jobs
Revises: 008_season_generated
Create Date: 2026-09-29 20:00:00.000000

- app_settings: settings edited from the admin panel (notifications, weekly
  summary, Telegram token and chats). Seeded from .env on the first start.
- job_runs: when each scheduled job last ran, so restarts neither repeat nor
  lose a run.
- users.telegram_id becomes unique (NULL, "not set", may repeat): the bot
  identifies people by it. Refuses to run if two accounts share one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '009_settings_jobs'
down_revision: Union[str, None] = '008_season_generated'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if 'app_settings' not in tables:
        op.create_table(
            'app_settings',
            sa.Column('key', sa.String(100), primary_key=True),
            sa.Column('value', sa.Text(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'),
                      server_onupdate=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_by', sa.Integer(), nullable=True),
        )
    if 'job_runs' not in tables:
        op.create_table(
            'job_runs',
            sa.Column('job', sa.String(100), primary_key=True),
            sa.Column('last_run_at', sa.DateTime(), nullable=False),
            sa.Column('last_status', sa.String(255), nullable=True),
        )

    duplicated = bind.execute(sa.text(
        'SELECT telegram_id, COUNT(*) FROM users WHERE telegram_id IS NOT NULL '
        'GROUP BY telegram_id HAVING COUNT(*) > 1'
    )).fetchall()
    if duplicated:
        listing = ', '.join(f'{row[0]} ({row[1]} accounts)' for row in duplicated)
        raise RuntimeError(f'Cannot make users.telegram_id unique, duplicated ids: {listing}')
    if not any(i.get('unique') and i['column_names'] == ['telegram_id'] for i in sa.inspect(bind).get_indexes('users')):
        op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])


def downgrade() -> None:
    op.drop_constraint('uq_users_telegram_id', 'users', type_='unique')
    op.drop_table('job_runs')
    op.drop_table('app_settings')
