"""prune tables no longer read by any code path

Revision ID: 005_prune_dead_tables
Revises: 004_merge_time_entries
Create Date: 2026-09-29 10:05:00.000000

None of these tables are queried anywhere in api/src (confirmed by grep):
- core_notifications, users_achievements_historical: always empty, no
  crud/router ever wrote to them. Dropped outright.
- time_entries_historical, time_entries_legacy, users_games_historical,
  games_statistics_historical, users_statistics_historical,
  users_games_2024: leftovers from the old Clockify era / a pre-`season`-column
  manual yearly-reset (rename-the-table) strategy. They do contain real rows,
  so they're renamed out of the active schema instead of dropped, in case
  that data is ever wanted later.

users_games_2024 and time_entries_legacy predate the current migration chain
(they aren't created by 001-004), so whether a given v1 backup has them
depends on how old it is - checked with has_table() rather than assumed.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '005_prune_dead_tables'
down_revision: Union[str, None] = '004_merge_time_entries'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ARCHIVE_RENAMES = [
    ('time_entries_historical', '_archived_time_entries_historical'),
    ('users_games_historical', '_archived_users_games_historical'),
    ('games_statistics_historical', '_archived_games_statistics_historical'),
    ('users_statistics_historical', '_archived_users_statistics_historical'),
]

# Predate the migration chain, so unlike the table above, their presence in a
# given backup isn't guaranteed - renamed only if actually found.
_OPTIONAL_ARCHIVE_RENAMES = [
    ('time_entries_legacy', '_archived_time_entries_legacy'),
    ('users_games_2024', '_archived_users_games_2024'),
]


def _rename_if_exists(inspector, old_name: str, new_name: str) -> None:
    if inspector.has_table(old_name):
        op.rename_table(old_name, new_name)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core_notifications")
    op.execute("DROP TABLE IF EXISTS users_achievements_historical")

    for old_name, new_name in _ARCHIVE_RENAMES:
        op.rename_table(old_name, new_name)

    inspector = inspect(op.get_bind())
    for old_name, new_name in _OPTIONAL_ARCHIVE_RENAMES:
        _rename_if_exists(inspector, old_name, new_name)


def downgrade() -> None:
    # core_notifications / users_achievements_historical were dropped with no
    # data (confirmed empty pre-migration); recreated empty on downgrade so
    # the ORM models keep working, not restored with data.
    op.execute(
        """
        CREATE TABLE core_notifications (
            notification VARCHAR(255) NOT NULL,
            PRIMARY KEY (notification),
            UNIQUE KEY notification (notification)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
        """
    )
    op.execute(
        """
        CREATE TABLE users_achievements_historical (
            id INT NOT NULL AUTO_INCREMENT,
            user_id INT DEFAULT NULL,
            achievement_id INT DEFAULT NULL,
            date DATE DEFAULT NULL,
            game_id VARCHAR(255) DEFAULT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY user_id (user_id, achievement_id, date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
        """
    )

    for old_name, new_name in _ARCHIVE_RENAMES:
        op.rename_table(new_name, old_name)

    inspector = inspect(op.get_bind())
    for old_name, new_name in _OPTIONAL_ARCHIVE_RENAMES:
        _rename_if_exists(inspector, new_name, old_name)
