"""user_settings: the player's own AI key (encrypted), its last characters and the model they chose

Revision ID: 056_user_ai_key
Revises: 055_ai_usage
Create Date: 2026-11-12 18:00:00.000000

A player can use their own OpenAI key for the chat and the game guide, so what they ask is paid from their account and
not from the group's. Three new columns on the player's personal settings:

  ai_api_key   the key, encrypted (Fernet, with a key derived from SECRET_KEY and bound to the player's id: see
               utils/user_ai.py). No API returns it, nobody can read it from the app, and a copy of the database is
               useless without the SECRET_KEY of the .env. A text column: the encrypted key is longer than the key.
  ai_key_hint  the last four characters of the key, so the player can tell which one they saved
  ai_model     the model the player chose for their key

All nullable: NULL means "no key of their own" (the group's is used, if the group's settings allow it). Purely additive:
nothing existing is rewritten, read or refused.

Re-runnable: each column is only added if it is missing.

Downgrade drops the three columns: the keys are lost and every player has to enter theirs again.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '056_user_ai_key'
down_revision: Union[str, None] = '055_ai_usage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'user_settings'
COLUMNS = (
    ('ai_api_key', sa.Text()),
    ('ai_key_hint', sa.String(4)),
    ('ai_model', sa.String(64)),
)


def _existing() -> set:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _existing()
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    existing = _existing()
    for name, _ in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
