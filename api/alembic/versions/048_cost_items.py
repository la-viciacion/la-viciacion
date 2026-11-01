"""cost_items: what the group spends to keep the app running, as rates with the dates they apply

Revision ID: 048_cost_items
Revises: 047_poll_added_options
Create Date: 2026-11-01 12:00:00.000000

The server page shows what the app costs. The server's own bill cannot be read from Hetzner (no billing API) and
the rest (the domain, anything that shows up later) is not in any API at all, so the history cannot be derived: it
has to be recorded. What is recorded is the *rate* and the days it applies, never a month's total, so the cost of
any month, year or the whole life is derived when asked (a price change in the middle of a month, a month with no
row and a back-filled past all come out right):

  cost_items  id, name, kind (server, domain or other: how the panel groups it), amount_cents (what the rate costs
              per `period`, VAT included, euros), hourly_micros (millionths of a euro per hour: only the server,
              which Hetzner bills by the hour up to its monthly price; NULL for the rest), period (month, year or
              once: a yearly cost is spread over twelve months, a one-off one counts in the month of `starts_on`),
              starts_on, ends_on (the last day it applies; NULL = still applies), source (manual, or hetzner: kept
              up to date by a daily job that closes the rate and opens another when Hetzner's price changes),
              external_id (the id of the Hetzner server a `hetzner` row follows), note, created_at

Purely additive: one new table, nothing existing is rewritten or refused.

Re-runnable: the table is only created if it is missing. Downgrade drops it (the recorded history is lost; the
Hetzner row is recreated, from today's price, by the daily job).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '048_cost_items'
down_revision: Union[str, None] = '047_poll_added_options'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'cost_items'


def upgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('hourly_micros', sa.Integer(), nullable=True),
        sa.Column('period', sa.String(10), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column('external_id', sa.String(64), nullable=True),
        sa.Column('note', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_cost_items_source', TABLE, ['source', 'external_id'])


def downgrade() -> None:
    if TABLE in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table(TABLE)
