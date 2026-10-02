"""backfill games_statistics and clean up known orphan/broken rows

Revision ID: 003_backfill_cleanup
Revises: 002_add_game_timers
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '003_backfill_cleanup'
down_revision: Union[str, None] = '002_add_game_timers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Any time_entries row can reference a Clockify project that was never
    # synced into `games` (this varies per environment/backup — found via a
    # LEFT JOIN, not a hardcoded id). Give each one a minimal placeholder row
    # so ranking/statistics code can resolve it; rename it from the app/front
    # once the real game is known.
    op.execute("""
        INSERT INTO games (id, name)
        SELECT DISTINCT te.project_clockify_id,
               CONCAT('Juego desconocido (', te.project_clockify_id, ')')
        FROM time_entries te
        LEFT JOIN games g ON g.id = te.project_clockify_id
        WHERE te.project_clockify_id IS NOT NULL AND g.id IS NULL
    """)

    # Rows with start/end/duration all NULL are abandoned timers with no
    # recoverable data; every existing query already filters them out
    # implicitly, so it's safe to drop them.
    op.execute("""
        DELETE FROM time_entries
        WHERE start IS NULL AND end IS NULL AND duration IS NULL
    """)

    # games_statistics only ever covered a fraction of `games`
    # (games_statistics_historical is the more complete table); backfill the
    # missing rows so games_most_played and related rankings see every game,
    # not just the ones that got a stats row early on.
    op.execute("""
        INSERT INTO games_statistics (game_id, played_time, avg_time, current_ranking)
        SELECT g.id, 0, g.avg_time, 1000000
        FROM games g
        LEFT JOIN games_statistics gs ON gs.game_id = g.id
        WHERE gs.game_id IS NULL
    """)

    # users_games_historical rows referencing a deleted game are left
    # untouched on purpose: nothing in the codebase joins that table against
    # `games`, so they're inert.


def downgrade() -> None:
    # Data cleanup, not meaningfully reversible.
    pass
