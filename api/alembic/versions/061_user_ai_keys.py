"""user_ai_vault, user_ai_keys and user_settings.ai_provider: a player's own keys for every provider, opened only with their password

Revision ID: 061_user_ai_keys
Revises: 060_ai_wallet
Create Date: 2026-11-14 18:00:00.000000

Until now a player could save one key, OpenAI's, in three columns of `user_settings`, encrypted with a key derived from the server's
`SECRET_KEY`: anybody who has the database and the `.env` (a snapshot of the whole server) can read it. The keys now go to a vault
that only the player's password opens (utils/ai_vault.py), and there is one per provider. Three additions:

  user_ai_vault   one row per player who has one: `record`, a JSON with the salt, the scrypt parameters and the data key wrapped with
                  their password. Nothing in it is a secret by itself.
  user_ai_keys    one row per player and provider: the key sealed with the data key (AES-256-GCM, bound to the player and the provider)
                  and the model they chose for it. The key is never readable from the row.
  user_settings.ai_provider   the provider the player prefers (NULL: the app picks, utils/ai_source.py). Not a secret.

Additive only: nothing existing is touched, read or refused. **The keys already saved are not moved here**: this migration cannot open
them into a vault because it does not know any password. Each one is adopted when its player logs in next (the server has their
password at that moment): it is opened with the old scheme, sealed in the new one and the old columns of that row are emptied. The
old columns (`ai_api_key`, `ai_key_hint`, `ai_model`) stay until every key has been adopted and a later migration removes them.

Both foreign keys are ON DELETE CASCADE: a deleted account takes its vault and its keys with it.

Re-runnable: each table and the column are only created if missing.

Downgrade drops the two tables and the column: the keys saved in the vault are lost (the players paste them again). The keys not yet
adopted are still in the old columns and keep working with the previous code.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '061_user_ai_keys'
down_revision: Union[str, None] = '060_ai_wallet'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VAULT = 'user_ai_vault'
KEYS = 'user_ai_keys'
SETTINGS = 'user_settings'
COLUMN = 'ai_provider'


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if VAULT not in tables:
        op.create_table(
            VAULT,
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('record', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('user_id'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_ai_vault_user', ondelete='CASCADE'),
        )
    if KEYS not in tables:
        op.create_table(
            KEYS,
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(length=20), nullable=False),
            sa.Column('secret', sa.Text(), nullable=False),
            sa.Column('model', sa.String(length=80), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('user_id', 'provider'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_ai_keys_user', ondelete='CASCADE'),
        )
    if COLUMN not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(SETTINGS)}:
        op.add_column(SETTINGS, sa.Column(COLUMN, sa.String(length=20), nullable=True))


def downgrade() -> None:
    if COLUMN in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(SETTINGS)}:
        op.drop_column(SETTINGS, COLUMN)
    for table in (KEYS, VAULT):
        if table in _tables():
            op.drop_table(table)
