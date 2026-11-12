"""ai_usage: what each call to the AI used and cost, and who paid for it

Revision ID: 055_ai_usage
Revises: 054_user_game_ids
Create Date: 2026-11-12 12:00:00.000000

Adds the table behind the AI's monitoring (chat, game guide). One row per call that a player asked for: when, who
(`user_id`, set to NULL if the account is deleted so what the group spent stays), the feature, whose key paid
(`key_source`: the group's from the .env, or the player's own), the provider and model, how it ended, the tokens (input,
cached, output, reasoning), the model calls, tool calls and web searches, how long it took, its cost in millionths of
a dollar at the prices of that day (NULL when the model's price was not known) and the date of those prices, the tools it
called (the kind of question it was), how long the question was and how many turns went with it. It keeps **no text** of
the question or of the answer. It is a record of events: nothing here can be derived from the other tables, and every
total the panels show is summed from it when asked.

Additive only: a new table, nothing existing is touched or read. The two foreign keys (`users`, `games`) are ON DELETE
SET NULL: deleting an account or a game must not be refused for its history, nor erase it.

`game_id` is created with the collation of `games.id` (read from information_schema): a foreign key needs both sides to
have the same one, and a table created now would take the server's default, which the older tables may not share (see
034_challenges and 016_foreign_keys).

Re-runnable: the table and each index are only created if missing.

Downgrade: drops the table (the record is lost).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '055_ai_usage'
down_revision: Union[str, None] = '054_user_game_ids'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'ai_usage'
INDEXES = (
    ('ix_ai_usage_created_at', ['created_at']),
    ('ix_ai_usage_user_created', ['user_id', 'created_at']),
    ('ix_ai_usage_source_created', ['key_source', 'created_at']),
)


def _games_id_collation() -> str | None:
    return op.get_bind().execute(sa.text(
        "SELECT collation_name FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'games' AND column_name = 'id'"
    )).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        _create_table()
    present = {index['name'] for index in sa.inspect(bind).get_indexes(TABLE)}
    for name, columns in INDEXES:
        if name not in present:
            op.create_index(name, TABLE, columns)


def _create_table() -> None:
    zero = sa.text('0')
    op.create_table(
        TABLE,
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('feature', sa.String(length=20), nullable=False),
        sa.Column('key_source', sa.String(length=10), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=True),
        sa.Column('model', sa.String(length=80), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('input_tokens', sa.Integer(), server_default=zero, nullable=False),
        sa.Column('cached_tokens', sa.Integer(), server_default=zero, nullable=False),
        sa.Column('output_tokens', sa.Integer(), server_default=zero, nullable=False),
        sa.Column('reasoning_tokens', sa.Integer(), server_default=zero, nullable=False),
        sa.Column('requests', sa.SmallInteger(), server_default=zero, nullable=False),
        sa.Column('tool_calls', sa.SmallInteger(), server_default=zero, nullable=False),
        sa.Column('web_searches', sa.SmallInteger(), server_default=zero, nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cost_micros', sa.Integer(), nullable=True),
        sa.Column('price_stamp', sa.DateTime(), nullable=True),
        sa.Column('tools', sa.String(length=255), nullable=True),
        sa.Column('question_chars', sa.SmallInteger(), nullable=True),
        sa.Column('turns', sa.SmallInteger(), nullable=True),
        sa.Column('game_id', sa.String(length=255, collation=_games_id_collation()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ai_usage_user', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], name='fk_ai_usage_game', ondelete='SET NULL'),
    )


def downgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table(TABLE)
