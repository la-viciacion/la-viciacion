"""backfill platform/season on game_timers rows merged from Clockify

Revision ID: 006_backfill_timer_platform
Revises: 005_prune_dead_tables
Create Date: 2026-09-29 11:00:00.000000

Migration 004 folded the old time_entries into game_timers, which has no
platform/season in the source, so every migrated session has both NULL. The
platform the user played each game on is recorded in users_games, and no user
has the same game on more than one platform, so (user_id, game_id) is enough to
recover it. Season is the calendar year of the session, which is how
users_games.season is defined. Sessions whose game has no users_games row keep
a NULL platform (nothing to infer it from).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '006_backfill_timer_platform'
down_revision: Union[str, None] = '005_prune_dead_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE game_timers t
        SET t.platform = (
            SELECT u.platform FROM users_games u
            WHERE u.user_id = t.user_id
              AND u.game_id = t.game_id
              AND u.platform IS NOT NULL
            LIMIT 1
        )
        WHERE t.platform IS NULL
        """
    )
    op.execute(
        "UPDATE game_timers SET season = YEAR(start_time) WHERE season IS NULL"
    )


def downgrade() -> None:
    # Not reversible: the backfilled values can't be told apart from native ones.
    pass
