"""password_resets: one-time links to recover a forgotten password

Revision ID: 017_password_resets
Revises: 016_foreign_keys
Create Date: 2026-09-30 21:00:00.000000

Adds the table behind "he olvidado mi contraseña". A row is a recovery link that was emailed
to a user: only the SHA-256 of the random token is stored (so a copy of the database cannot be
used to take over an account), with its creation and expiry times (UTC) and, once used, when.
It belongs to its user: deleting the user deletes their links (ON DELETE CASCADE).

Additive only: a new table, nothing existing is touched or read. Re-runnable: it does nothing if
the table is already there.

Downgrade: drops the table. Unused links are worthless after a restore anyway.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017_password_resets'
down_revision: Union[str, None] = '016_foreign_keys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'password_resets' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'password_resets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_password_resets_token'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_password_resets_user', ondelete='CASCADE'),
    )
    op.create_index('ix_password_resets_user_id', 'password_resets', ['user_id'])


def downgrade() -> None:
    if 'password_resets' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('password_resets')
