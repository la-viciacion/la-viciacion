"""The schema of a v1 database (before migration 000), as `mariadb-dump --no-data` wrote it.

Taken from a real v1 backup: DDL only, no data (the AUTO_INCREMENT counters, which say how many rows
existed, are removed). It includes what a v1 database had and the migration chain later drops or
archives (`logs`, `request_sync`, `other_tags`, `core_notifications`, the `*_historical` and
`*_2024`/`*_legacy` tables, the Clockify columns), which migration 000 does not create because
a database that starts empty never needs them. Applied migrations are immutable, so this stays valid
forever; it is the starting point of tests/test_mariadb_v1_upgrade.py.
"""

# table name -> CREATE TABLE statement, in the order the dump listed them
V1_TABLES = {
    "achievements": """
CREATE TABLE `achievements` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `key` varchar(255) DEFAULT NULL,
  `title` varchar(255) DEFAULT NULL,
  `message` varchar(255) DEFAULT NULL,
  `image` longblob DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "core_notifications": """
CREATE TABLE `core_notifications` (
  `notification` varchar(255) NOT NULL,
  PRIMARY KEY (`notification`),
  UNIQUE KEY `notification` (`notification`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "games": """
CREATE TABLE `games` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "games_statistics": """
CREATE TABLE `games_statistics` (
  `game_id` varchar(255) NOT NULL,
  `played_time` int(11) DEFAULT NULL,
  `avg_time` int(11) DEFAULT NULL,
  `current_ranking` int(11) DEFAULT NULL,
  PRIMARY KEY (`game_id`),
  UNIQUE KEY `game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "games_statistics_historical": """
CREATE TABLE `games_statistics_historical` (
  `game_id` varchar(255) NOT NULL,
  `played_time` int(11) DEFAULT NULL,
  `avg_time` int(11) DEFAULT NULL,
  `current_ranking` int(11) DEFAULT NULL,
  PRIMARY KEY (`game_id`),
  UNIQUE KEY `game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "logs": """
CREATE TABLE `logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `player` varchar(255) DEFAULT NULL,
  `action` varchar(255) DEFAULT NULL,
  `date` datetime DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "other_tags": """
CREATE TABLE `other_tags` (
  `id` varchar(255) NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "platform_tags": """
CREATE TABLE `platform_tags` (
  `id` varchar(255) NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "request_sync": """
CREATE TABLE `request_sync` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `request_id` varchar(255) NOT NULL,
  PRIMARY KEY (`id`,`request_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "time_entries": """
CREATE TABLE `time_entries` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "time_entries_historical": """
CREATE TABLE `time_entries_historical` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "time_entries_legacy": """
CREATE TABLE `time_entries_legacy` (
  `id` varchar(255) DEFAULT NULL,
  `user_id` int(11) DEFAULT NULL,
  `user_clockify_id` varchar(255) DEFAULT NULL,
  `project_clockify_id` varchar(255) DEFAULT NULL,
  `games_name` varchar(255) DEFAULT NULL,
  `start` varchar(255) DEFAULT NULL,
  `end` varchar(255) DEFAULT NULL,
  `duration` double DEFAULT NULL,
  `tags` varchar(255) DEFAULT NULL,
  `completed` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users": """
CREATE TABLE `users` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
""",
    "users_achievements": """
CREATE TABLE `users_achievements` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `achievement_id` int(11) DEFAULT NULL,
  `date` date DEFAULT NULL,
  `game_id` varchar(255) DEFAULT NULL,
  `season` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`achievement_id`,`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_achievements_historical": """
CREATE TABLE `users_achievements_historical` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) DEFAULT NULL,
  `achievement_id` int(11) DEFAULT NULL,
  `date` date DEFAULT NULL,
  `game_id` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`achievement_id`,`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_games": """
CREATE TABLE `users_games` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_games_2024": """
CREATE TABLE `users_games_2024` (
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
  `season` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_id` (`user_id`,`game_id`,`platform`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_games_historical": """
CREATE TABLE `users_games_historical` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_statistics": """
CREATE TABLE `users_statistics` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
    "users_statistics_historical": """
CREATE TABLE `users_statistics_historical` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
""",
}
