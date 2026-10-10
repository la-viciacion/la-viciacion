"""the keys of outside services stop being stored: they are read from the environment

Revision ID: 035_secrets_env_only
Revises: 034_challenges
Create Date: 2026-10-10 18:00:00.000000

`app_settings` held the bot token (encrypted), the group id and the admin chat id, and the AI key (encrypted),
seeded from `.env` the first time. A copy of the database (a backup, a dump loaded on a laptop) then carried the
means to run the group's bot and to spend the AI quota. From this revision the application reads
`TELEGRAM_TOKEN`, `TELEGRAM_GROUP_ID`, `TELEGRAM_ADMIN_CHAT_ID` and `AI_API_KEY` from the environment every time and
never writes them, so this migration deletes the four rows.

**Decision: it deletes data, on purpose.** Only the rows `telegram.token`, `telegram.group_id`,
`telegram.admin_chat_id` and `ai.api_key`, and nothing else in the table (the AI provider and model stay). Before
deploying it the `.env` of the environment must have the variables (the bot does not start without the token and the
group; the API does, and says in the panel what is missing), because after it the database no longer has them. Take
the backup of the deployment first, as with any migration, and note that the backup itself still holds the rows, so
it should be kept as carefully as the `.env`.

It refuses nothing (there is no data it could find inconsistent) and running it again does nothing.

Downgrade: cannot restore the rows (the values are not recoverable, and they should not be); it leaves the table as
it is. The previous code seeds them again from `.env` on its next start, because the rows are missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '035_secrets_env_only'
down_revision: Union[str, None] = '034_challenges'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KEYS = ('telegram.token', 'telegram.group_id', 'telegram.admin_chat_id', 'ai.api_key')


def upgrade() -> None:
    bind = op.get_bind()
    if 'app_settings' not in sa.inspect(bind).get_table_names():
        return
    for key in KEYS:
        bind.execute(sa.text('DELETE FROM app_settings WHERE `key` = :key'), {'key': key})


def downgrade() -> None:
    # the old code reads them from .env again when the rows are missing; the stored values are not brought back
    pass
