"""baseline: the v1 tables that migrations 001-014 start from

Revision ID: 000_baseline_v1
Revises: None
Create Date: 2026-09-30 17:00:00.000000

Migrations 001-014 were written to upgrade a database imported from a v1 backup, so
they assume the v1 tables exist (001 alters `games`, 003 reads `time_entries`, 005
renames the `*_historical` tables...). On a database that has no tables at all, which
is what a new deployment starts with, `alembic upgrade head` failed at 001. This
revision creates those tables, so that an empty database walks the same path as a v1
backup and ends in the same schema.

What it creates (the exact v1 DDL, taken from a v1 backup): `achievements`, `games`,
`games_statistics`, `games_statistics_historical`, `platform_tags`, `time_entries`,
`time_entries_historical`, `users`, `users_achievements`, `users_games`,
`users_games_historical` and `users_statistics_historical`. Only what the chain needs:
the other v1 tables (`logs`, `request_sync`, `other_tags`, `users_statistics`,
`core_notifications`, ...) are dropped or ignored by later migrations, so they are
not created just to be deleted.

Idempotent and non-destructive: each table is created only if it does not exist, and
nothing that exists is ever altered. On a database imported from a v1 backup (or one
already migrated) every table is there and this revision does nothing. Later
migrations turn these tables into the current schema; the empty `_archived_*` tables
that 005 leaves behind on a new deployment are harmless.

Downgrade: irreversible on purpose. Dropping these tables would delete data on any
database that has been in use.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '000_baseline_v1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GENERAL = 'DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci'
UNICODE = 'DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'

_GAMES_STATISTICS = """
    `game_id` varchar(255) NOT NULL,
    `played_time` int(11) DEFAULT NULL,
    `avg_time` int(11) DEFAULT NULL,
    `current_ranking` int(11) DEFAULT NULL,
    PRIMARY KEY (`game_id`),
    UNIQUE KEY `game_id` (`game_id`)
"""

_TIME_ENTRIES = """
    `id` varchar(255) NOT NULL,
    `user_id` int(11) DEFAULT NULL,
    `user_clockify_id` varchar(255) DEFAULT NULL,
    `project_clockify_id` varchar(255) DEFAULT NULL,
    `start` datetime DEFAULT NULL,
    `end` datetime DEFAULT NULL,
    `duration` int(11) DEFAULT NULL,
    `tags` varchar(255) DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `id` (`id`)
"""

_USERS_GAMES_HISTORICAL = """
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `user_id` int(11) DEFAULT NULL,
    `game_id` varchar(255) DEFAULT NULL,
    `started_date` date DEFAULT NULL,
    `platform` varchar(255) DEFAULT NULL,
    `completed` int(11) DEFAULT NULL,
    `completed_date` date DEFAULT NULL,
    `score` float DEFAULT NULL,
    `played_time` int(11) DEFAULT NULL,
    `completion_time` int(11) DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `user_id` (`user_id`,`game_id`,`platform`)
"""

_USERS_STATISTICS = """
    `user_id` int(11) NOT NULL AUTO_INCREMENT,
    `played_time` int(11) DEFAULT NULL,
    `current_ranking_hours` int(11) DEFAULT NULL,
    `current_streak` int(11) DEFAULT NULL,
    `best_streak` int(11) DEFAULT NULL,
    `best_streak_date` date DEFAULT NULL,
    `played_days` int(11) DEFAULT NULL,
    `best_unplayed_streak` int(11) DEFAULT NULL,
    `played_games` int(11) DEFAULT NULL,
    `completed_games` int(11) DEFAULT NULL,
    `current_unplayed_streak` int(11) DEFAULT NULL,
    `best_unplayed_streak_date` date DEFAULT NULL,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `user_id` (`user_id`)
"""

# (table, column definitions, charset clause). Constants of this file: never user data.
TABLES = [
    ('achievements', """
        `id` int(11) NOT NULL AUTO_INCREMENT,
        `key` varchar(255) DEFAULT NULL,
        `title` varchar(255) DEFAULT NULL,
        `message` varchar(255) DEFAULT NULL,
        `image` longblob DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `key` (`key`)
    """, GENERAL),
    ('games', """
        `id` varchar(255) NOT NULL,
        `name` varchar(255) DEFAULT NULL,
        `dev` varchar(255) DEFAULT NULL,
        `release_date` date DEFAULT NULL,
        `steam_id` varchar(255) DEFAULT NULL,
        `image_url` varchar(255) DEFAULT NULL,
        `genres` varchar(255) DEFAULT NULL,
        `avg_time` int(11) DEFAULT NULL,
        `slug` varchar(255) DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `name` (`name`)
    """, GENERAL),
    ('games_statistics', _GAMES_STATISTICS, GENERAL),
    ('games_statistics_historical', _GAMES_STATISTICS, GENERAL),
    ('platform_tags', """
        `id` varchar(255) NOT NULL,
        `name` varchar(255) DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `id` (`id`)
    """, GENERAL),
    ('time_entries', _TIME_ENTRIES, GENERAL),
    ('time_entries_historical', _TIME_ENTRIES, GENERAL),
    ('users', """
        `id` int(11) NOT NULL AUTO_INCREMENT,
        `name` varchar(255) DEFAULT NULL,
        `username` varchar(255) DEFAULT NULL,
        `telegram_id` bigint(20) DEFAULT NULL,
        `clockify_id` varchar(255) DEFAULT NULL,
        `is_admin` int(11) DEFAULT NULL,
        `password` varchar(255) DEFAULT NULL,
        `is_active` int(11) DEFAULT NULL,
        `email` varchar(255) DEFAULT NULL,
        `avatar` longblob DEFAULT NULL,
        `clockify_key` varchar(255) DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `telegram_username` (`username`)
    """, UNICODE),
    ('users_achievements', """
        `id` int(11) NOT NULL AUTO_INCREMENT,
        `user_id` int(11) DEFAULT NULL,
        `achievement_id` int(11) DEFAULT NULL,
        `date` date DEFAULT NULL,
        `game_id` varchar(255) DEFAULT NULL,
        `season` int(11) DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `user_id` (`user_id`,`achievement_id`,`date`)
    """, GENERAL),
    ('users_games', """
        `id` int(11) NOT NULL AUTO_INCREMENT,
        `user_id` int(11) DEFAULT NULL,
        `game_id` varchar(255) DEFAULT NULL,
        `started_date` date DEFAULT NULL,
        `season` int(11) DEFAULT NULL,
        `platform` varchar(255) DEFAULT NULL,
        `completed` int(11) DEFAULT NULL,
        `completed_date` date DEFAULT NULL,
        `score` float DEFAULT NULL,
        `played_time` int(11) DEFAULT NULL,
        `completion_time` int(11) DEFAULT NULL,
        PRIMARY KEY (`id`),
        UNIQUE KEY `user_id` (`user_id`,`game_id`,`platform`,`season`)
    """, GENERAL),
    ('users_games_historical', _USERS_GAMES_HISTORICAL, GENERAL),
    ('users_statistics_historical', _USERS_STATISTICS, GENERAL),
]


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table, columns, charset in TABLES:
        if table not in existing:
            op.execute(f'CREATE TABLE `{table}` ({columns}) ENGINE=InnoDB {charset}')


def downgrade() -> None:
    raise RuntimeError('irreversible: this revision only creates the v1 tables, and dropping them would delete data')
