"""user_ai_vault, user_ai_keys and user_settings.ai_provider: a player's own keys for every provider, opened only with their password

Revision ID: 061_user_ai_keys
Revises: 060_ai_wallet
Create Date: 2026-11-14 18:00:00.000000

Until now a player could save one key, OpenAI's, in three columns of `user_settings` (`ai_api_key`, `ai_key_hint`, `ai_model`), encrypted with a
key derived from the server's `SECRET_KEY`: anybody who has the database and the `.env` (a snapshot of the whole server) can read it. The keys
now go to a vault that only the player's password opens (utils/ai_vault.py), and there is one per provider. Three additions and one removal:

  user_ai_vault   one row per player who has one: `record`, a JSON with the salt, the scrypt parameters and the data key wrapped with
                  their password. Nothing in it is a secret by itself.
  user_ai_keys    one row per player and provider: the key sealed with the data key (AES-256-GCM, bound to the player and the provider)
                  and the model they chose for it. The key is never readable from the row.
  user_settings.ai_provider   the provider the player prefers (NULL: the app picks, utils/ai_source.py). Not a secret.
  user_settings.ai_api_key, ai_key_hint, ai_model   dropped. **A decision of the owner of the project: nobody had saved a key**, so there is
                  nothing to move into the vault and the code that would have adopted them is not written. It still refuses instead of deleting:
                  if any `ai_api_key` holds a value the migration stops, changing nothing, and says how many players have one (they would lose it:
                  empty the column, or ask them to paste it again afterwards).

The two tables are additive and both foreign keys are ON DELETE CASCADE (a deleted account takes its vault and its keys with it). The refusal
is the first phase, before anything changes; each step is only done if missing, so it can be run again.

Downgrade puts the three old columns back, empty, and drops the two tables and `ai_provider`: the keys in the vault are lost (the players
paste them again) and the old code never saw them.
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
OLD = (('ai_api_key', sa.Text()), ('ai_key_hint', sa.String(length=4)), ('ai_model', sa.String(length=64)))


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(SETTINGS)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns()
    if 'ai_api_key' in columns:  # first phase: read only
        held = bind.execute(sa.text(f"SELECT COUNT(*) FROM {SETTINGS} WHERE ai_api_key IS NOT NULL")).scalar()
        if held:
            raise RuntimeError(
                f"Migration 061 refuses to drop user_settings.ai_api_key: {held} player(s) still have a key saved there, and it would be lost. "
                "Nothing was changed. Empty the column (UPDATE user_settings SET ai_api_key = NULL, ai_key_hint = NULL, ai_model = NULL) "
                "after telling those players to save their key again, then restart the API."
            )
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
    if COLUMN not in columns:
        op.add_column(SETTINGS, sa.Column(COLUMN, sa.String(length=20), nullable=True))
    for name, _ in OLD:
        if name in columns:
            op.drop_column(SETTINGS, name)


def downgrade() -> None:
    columns = _columns()
    for name, kind in OLD:
        if name not in columns:
            op.add_column(SETTINGS, sa.Column(name, kind, nullable=True))
    if COLUMN in columns:
        op.drop_column(SETTINGS, COLUMN)
    for table in (KEYS, VAULT):
        if table in _tables():
            op.drop_table(table)
