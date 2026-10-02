"""merge time_entries (Clockify-era sessions) into game_timers

Revision ID: 004_merge_time_entries
Revises: 003_backfill_cleanup
Create Date: 2026-09-29 10:00:00.000000

Folds the old Clockify `time_entries` rows into `game_timers` as finished
(is_active=0) sessions, so every session lives in one table and the app no
longer needs to UNION two schemas with different collations to compute
stats/rankings. The original table is kept, renamed out of the way, instead
of dropped outright, so the raw Clockify data isn't permanently lost if it's
ever needed again.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '004_merge_time_entries'
down_revision: Union[str, None] = '003_backfill_cleanup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # game_timers.game_id was created without an explicit collation (server
    # default), which is what forced the .collate("utf8mb4_general_ci") hack
    # in sessions_subquery(). Align it with games.id/users_games.game_id now
    # that it's about to become the only sessions table.
    op.execute(
        "ALTER TABLE game_timers "
        "MODIFY game_id VARCHAR(255) COLLATE utf8mb4_general_ci NOT NULL"
    )

    # Every remaining time_entries row (migration 003 already dropped the
    # fully-empty ones) becomes a finished native session. tags/user_clockify_id
    # have no equivalent column and nothing in the app ever reads them, so
    # they're dropped rather than shoehorned into `notes`.
    #
    # A handful of (user_id, project_clockify_id, start) groups have more than
    # one row - accidental double-starts in Clockify a few seconds apart, per
    # a real backup checked during development. game_timers' unique
    # constraint on that same triple would reject the second one, so keep
    # only the most complete row (highest duration) per group.
    op.execute(
        """
        INSERT INTO game_timers (user_id, game_id, start_time, end_time, duration_seconds, is_active)
        SELECT user_id, project_clockify_id, start, end, duration, 0
        FROM (
            SELECT
                user_id, project_clockify_id, start, end, duration,
                ROW_NUMBER() OVER (
                    PARTITION BY user_id, project_clockify_id, start
                    ORDER BY duration DESC, id DESC
                ) AS rn
            FROM time_entries
            WHERE start IS NOT NULL
        ) ranked
        WHERE rn = 1
        """
    )

    op.rename_table('time_entries', '_archived_time_entries')


def downgrade() -> None:
    op.rename_table('_archived_time_entries', 'time_entries')
    # The backfilled game_timers rows are intentionally left in place; there is
    # no reliable way to tell them apart from native rows once merged.
    op.execute(
        "ALTER TABLE game_timers MODIFY game_id VARCHAR(255) NOT NULL"
    )
