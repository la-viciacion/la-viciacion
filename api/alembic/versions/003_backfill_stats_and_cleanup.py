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
    # A time_entries row references a Clockify project that was never synced
    # into `games` (id '6a77572adaa44a80c5b1c873'). Give it a minimal
    # placeholder row so ranking/statistics code can resolve it; rename it
    # from the app/front once the real game is known.
    op.execute("""
        INSERT INTO games (id, name)
        SELECT '6a77572adaa44a80c5b1c873', 'Juego desconocido (Clockify)'
        WHERE NOT EXISTS (
            SELECT 1 FROM games WHERE id = '6a77572adaa44a80c5b1c873'
        )
    """)

    # One time_entries row has start/end/duration all NULL (an abandoned
    # timer with no recoverable data); every existing query already filters
    # it out implicitly, so it's safe to drop.
    op.execute("""
        DELETE FROM time_entries
        WHERE start IS NULL AND end IS NULL AND duration IS NULL
    """)

    # games_statistics only covers a fraction of `games` (games_statistics_historical
    # is the more complete table); backfill the missing rows so games_most_played
    # and related rankings see every game, not just the ones synced early on.
    op.execute("""
        INSERT INTO games_statistics (game_id, played_time, avg_time, current_ranking)
        SELECT g.id, 0, g.avg_time, 1000000
        FROM games g
        LEFT JOIN games_statistics gs ON gs.game_id = g.id
        WHERE gs.game_id IS NULL
    """)

    # The `users_games_historical` row referencing a deleted game
    # ('66578a821069d616f6568924') is left untouched on purpose: nothing in
    # the codebase joins that table against `games`, so it's inert.


def downgrade() -> None:
    # Data cleanup, not meaningfully reversible.
    pass
