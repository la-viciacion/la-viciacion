"""audit_log: what an admin changed from the admin panel

Revision ID: 022_audit_log
Revises: 021_wishlist
Create Date: 2026-10-04 18:00:00.000000

Adds the table behind the admin panel's activity log (Sistema -> Registro). One row per successful write
of the admin API: when, who (the key and the name, which stays if the account is deleted), the HTTP method
and path, the entity and row touched, the status and a JSON `detail` (the row as it was, what was sent with
secrets hidden). It is the record of a decision, so it is stored and not derived.

Additive only: a new table, nothing existing is touched or read. `user_id` is a foreign key to `users` with
ON DELETE SET NULL (deleting an account must not erase the trace of what it did, nor be refused for it).

Re-runnable: the table and each index are only created if missing.

Downgrade: drops the table (the log is lost).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '022_audit_log'
down_revision: Union[str, None] = '021_wishlist'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'audit_log'
INDEXES = (('ix_audit_log_created_at', 'created_at'), ('ix_audit_log_entity', 'entity'))


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        _create_table()
    present = {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}
    for name, column in INDEXES:
        if name not in present:
            op.create_index(name, TABLE, [column])


def _create_table() -> None:
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('entity', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.SmallInteger(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_audit_log_user', ondelete='SET NULL'),
    )


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
