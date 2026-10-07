"""Migrations and schema rules checked on a real MariaDB (see tests/mariadb_db.py).

`test_migrations.py` only inspects the files; these run them. They cover an older revision with data
taken to the head (step 3 of the verification checklist in docs/migrations.md) plus the rules that only
MariaDB enforces. Empty -> head, re-run, downgrade and back, and the models matching the schema are in
`test_mariadb_migration_chain.py`, for every migration. The checklist's step 3 with a copy of the
production backup stays manual: it needs real data.
"""
import datetime

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.mariadb_db import MariaDBTestCase
from tests.test_migrations import load_script_directory

# Old enough to be a fixed point (applied migrations are immutable, so data seeded at this revision
# stays valid forever) and recent enough that every later migration upgrades real-looking tables.
SEEDED_REVISION = "016_foreign_keys"


def head_revision() -> str:
    return load_script_directory().get_current_head()


class SchemaRulesTests(MariaDBTestCase):
    """The constraints the application relies on, enforced by the database itself."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate()
        with cls.engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, username, email) VALUES (1, 'ana', 'ana@example.com')"))
            conn.execute(text("INSERT INTO games (id, name) VALUES ('g1', 'Game One')"))

    def execute(self, sql, **params):
        with self.engine.begin() as conn:
            return conn.execute(text(sql), params)

    def test_season_is_generated_by_the_database_from_the_date(self):
        # the three tables that derive it (rule 2 of AGENTS.md)
        for table, column in (("users_games", "season"), ("game_timers", "season"), ("users_achievements", "season")):
            extra = {c["name"]: c for c in inspect(self.engine).get_columns(table)}[column]
            self.assertIsNotNone(extra.get("computed"), f"{table}.{column} must be a generated column")

    def test_season_follows_the_date_and_cannot_be_written(self):
        self.execute(
            "INSERT INTO game_timers (user_id, game_id, start_time, platform) VALUES "
            "(1, 'g1', '2025-12-31 23:30:00', 'pc'), (1, 'g1', '2026-01-01 00:30:00', 'pc')"
        )
        seasons = [
            row[0] for row in self.execute(
                "SELECT season FROM game_timers WHERE start_time >= '2025-12-31' ORDER BY start_time"
            )
        ]
        self.assertEqual(seasons, [2025, 2026])
        with self.assertRaises(DBAPIError):
            self.execute(
                "INSERT INTO game_timers (user_id, game_id, start_time, season) VALUES (1, 'g1', '2030-05-05', 1999)"
            )

    def test_a_library_entry_is_unique_per_game_platform_and_season(self):
        insert = "INSERT INTO users_games (user_id, game_id, platform, started_date) VALUES (1, 'g1', 'pc', :d)"
        self.execute(insert, d=datetime.date(2024, 3, 1))
        with self.assertRaises(IntegrityError):
            self.execute(insert, d=datetime.date(2024, 11, 20))
        self.execute(insert, d=datetime.date(2025, 3, 1))  # another season is another entry

    def test_foreign_keys_refuse_orphans(self):
        with self.assertRaises(IntegrityError):
            self.execute("INSERT INTO game_timers (user_id, game_id, start_time) VALUES (999, 'g1', '2026-01-01')")
        with self.assertRaises(IntegrityError):
            self.execute("INSERT INTO game_timers (user_id, game_id, start_time) VALUES (1, 'nope', '2026-01-01')")

    def test_user_identifiers_are_unique(self):
        with self.assertRaises(IntegrityError):
            self.execute("INSERT INTO users (username, email) VALUES ('other', 'ana@example.com')")
        with self.assertRaises(IntegrityError):
            self.execute("INSERT INTO users (username, email) VALUES ('ana', 'other@example.com')")

    def test_the_refresh_interval_check_refuses_less_than_ten_minutes(self):
        self.execute("INSERT INTO users (id, username, email) VALUES (50, 'bea', 'bea@example.com')")
        self.execute("INSERT INTO user_settings (user_id, timer_notice_minutes) VALUES (50, 10)")
        with self.assertRaises(DBAPIError):
            self.execute("UPDATE user_settings SET timer_notice_minutes = 5 WHERE user_id = 50")
        with self.assertRaises(DBAPIError):
            self.execute("UPDATE user_settings SET timer_notice_minutes = 121 WHERE user_id = 50")

    def test_a_score_is_one_to_a_hundred_once_per_user_and_game(self):
        self.execute("INSERT INTO users (id, username, email) VALUES (60, 'dai', 'dai@example.com')")
        self.execute("INSERT INTO games (id, name) VALUES ('gs1', 'Score Game')")
        self.execute("INSERT INTO game_scores (user_id, game_id, score) VALUES (60, 'gs1', 100)")
        for sql in (
            "INSERT INTO game_scores (user_id, game_id, score) VALUES (60, 'gs1', 50)",  # once per user and game
            "UPDATE game_scores SET score = 0 WHERE user_id = 60",
            "UPDATE game_scores SET score = 101 WHERE user_id = 60",
            "INSERT INTO game_scores (user_id, game_id, score) VALUES (999, 'gs1', 5)",  # unknown user
            "INSERT INTO game_scores (user_id, game_id, score) VALUES (60, 'nope', 5)",  # unknown game
        ):
            with self.subTest(sql), self.assertRaises((IntegrityError, DBAPIError)):
                self.execute(sql)

    def test_a_wish_is_once_per_user_and_game_and_needs_both(self):
        self.execute("INSERT INTO users (id, username, email) VALUES (61, 'eli', 'eli@example.com')")
        self.execute("INSERT INTO games (id, name) VALUES ('wl1', 'Wish Game')")
        self.execute("INSERT INTO users_wishlist (user_id, game_id) VALUES (61, 'wl1')")
        for sql in (
            "INSERT INTO users_wishlist (user_id, game_id) VALUES (61, 'wl1')",  # once per user and game
            "INSERT INTO users_wishlist (user_id, game_id) VALUES (999, 'wl1')",  # unknown user
            "INSERT INTO users_wishlist (user_id, game_id) VALUES (61, 'nope')",  # unknown game
        ):
            with self.subTest(sql), self.assertRaises(IntegrityError):
                self.execute(sql)

    def test_deleting_a_user_removes_their_settings(self):
        self.execute("INSERT INTO users (id, username, email) VALUES (51, 'cai', 'cai@example.com')")
        self.execute("INSERT INTO user_settings (user_id) VALUES (51)")
        self.execute("DELETE FROM users WHERE id = 51")
        self.assertEqual(self.execute("SELECT COUNT(*) FROM user_settings WHERE user_id = 51").scalar(), 0)


class AchievementLevelsTests(MariaDBTestCase):
    """029 gives the special level and the secret mark of the code to the rows an installation has, once, and
    never over what an admin chose."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate("028_achievement_special")
        with cls.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO achievements (`key`, title, message, special, secret) VALUES "
                "('PLAYED_12_HOURS_DAY', 'a', 'm', 0, 0), "     # special in the code: it gets its level
                "('PLAYED_16_HOURS_DAY', 'b', 'm', 3, 0), "     # an admin made it purple: it stays purple
                "('JUST_IN_TIME', 'c', 'm', 0, 0), "            # special and secret in the code
                "('EARLY_RISER', 'd', 'm', 0, 0), "             # secret only
                "('PLAYED_7_DAYS', 'e', 'm', 0, 1), "           # not in the code's list: an admin's mark stays
                "('SOMETHING_THE_CODE_DROPPED', 'f', 'm', 0, 0)"  # unknown: untouched
            ))
        cls.migrate()

    def state(self, key):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT special, secret FROM achievements WHERE `key` = :k"), {"k": key}).one()
        return row.special, bool(row.secret)

    def test_the_rows_at_their_default_get_what_the_code_says(self):
        self.assertEqual(self.state("PLAYED_12_HOURS_DAY"), (1, True))  # 029 gave it the level, 033 (up to the head) made it secret
        self.assertEqual(self.state("JUST_IN_TIME"), (1, True))
        self.assertEqual(self.state("EARLY_RISER"), (0, True))

    def test_what_an_admin_chose_is_never_overwritten(self):
        self.assertEqual(self.state("PLAYED_16_HOURS_DAY"), (3, False))
        self.assertEqual(self.state("PLAYED_7_DAYS"), (0, True))

    def test_what_the_code_does_not_know_is_left_alone_and_nothing_is_inserted(self):
        self.assertEqual(self.state("SOMETHING_THE_CODE_DROPPED"), (0, False))
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM achievements")).scalar(), 6)


class AchievementReviewTests(MariaDBTestCase):
    """033 brings the level and the secret mark of the rows an installation has to the reviewed catalogue, once, and
    never over what an admin chose."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate("032_weather_days")
        with cls.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO achievements (`key`, title, message, special, secret) VALUES "
                "('PLAYED_100_HOURS_GAME', 'a', 'm', 0, 0), "                 # at the old level: it is raised
                "('PLAYED_50_GAMES', 'b', 'm', 3, 0), "                       # an admin made it purple: it stays purple
                "('PLAYED_1000_HOURS_GAME_LIFETIME', 'c', 'm', 1, 0), "      # silver in the old code: now gold
                "('SOLAR_ECLIPSE_LIFETIME', 'd', 'm', 0, 1), "               # created without a level
                "('PLAYED_4_HOURS_SESSION', 'e', 'm', 0, 0), "               # now secret
                "('PLAYED_7_DAYS', 'f', 'm', 0, 1), "                        # not in the list: an admin's mark stays
                "('SOMETHING_THE_CODE_DROPPED', 'g', 'm', 0, 0)"             # unknown: untouched
            ))
        cls.migrate()

    def state(self, key):
        with self.engine.connect() as conn:
            row = conn.execute(text("SELECT special, secret FROM achievements WHERE `key` = :k"), {"k": key}).one()
        return row.special, bool(row.secret)

    def test_the_rows_at_the_old_values_get_what_the_code_says(self):
        self.assertEqual(self.state("PLAYED_100_HOURS_GAME"), (1, False))
        self.assertEqual(self.state("PLAYED_1000_HOURS_GAME_LIFETIME"), (2, False))
        self.assertEqual(self.state("SOLAR_ECLIPSE_LIFETIME"), (3, True))
        self.assertEqual(self.state("PLAYED_4_HOURS_SESSION"), (0, True))

    def test_what_an_admin_chose_is_never_overwritten(self):
        self.assertEqual(self.state("PLAYED_50_GAMES"), (3, False))
        self.assertEqual(self.state("PLAYED_7_DAYS"), (0, True))

    def test_what_the_code_does_not_know_is_left_alone_and_nothing_is_inserted(self):
        self.assertEqual(self.state("SOMETHING_THE_CODE_DROPPED"), (0, False))
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM achievements")).scalar(), 7)


class UpgradeFromAnOlderRevisionTests(MariaDBTestCase):
    """A database that already has data (what production is) must survive the migrations after it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate(SEEDED_REVISION)
        with cls.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO users (id, name, username, email, is_admin, is_active, telegram_id) VALUES "
                "(1, 'Ana', 'ana', 'ana@example.com', 1, 1, 111), (2, 'Bea', 'bea', 'bea@example.com', 0, 1, NULL)"
            ))
            conn.execute(text("INSERT INTO games (id, name, avg_time) VALUES ('g1', 'Game One', 36000), ('g2', 'Game Two', 7200)"))
            conn.execute(text(
                "INSERT INTO users_games (user_id, game_id, platform, started_date, completed, completed_date, score) VALUES "
                "(1, 'g1', 'pc', '2025-02-01', 1, '2025-03-01', 8.5), (1, 'g1', 'pc', '2026-01-10', 0, NULL, NULL), "
                "(2, 'g2', 'switch', '2026-05-05', 0, NULL, NULL)"
            ))
            conn.execute(text(
                "INSERT INTO game_timers (user_id, game_id, start_time, end_time, duration_seconds, platform, is_active) VALUES "
                "(1, 'g1', '2025-02-01 20:00:00', '2025-02-01 22:00:00', 7200, 'pc', 0), "
                "(2, 'g2', '2026-05-05 18:00:00', NULL, NULL, 'switch', 1)"
            ))
            conn.execute(text("INSERT INTO achievements (id, `key`, title, message) VALUES (1, 'first', 'First', 'Welcome')"))
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date, game_id) VALUES (1, 1, '2025-02-01', 'g1')"))
        cls.migrate()

    def scalar(self, sql):
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

    def test_it_reaches_head(self):
        self.assertEqual(self.current_revision(), head_revision())

    def test_no_row_is_lost(self):
        for table, expected in (
            ("users", 2), ("games", 2), ("users_games", 3), ("game_timers", 2), ("users_achievements", 1),
        ):
            self.assertEqual(self.scalar(f"SELECT COUNT(*) FROM {table}"), expected, table)

    def test_values_survive(self):
        self.assertEqual(self.scalar("SELECT telegram_id FROM users WHERE username = 'ana'"), 111)
        self.assertEqual(self.scalar("SELECT completed FROM users_games WHERE user_id = 1 AND season = 2025"), 1)
        self.assertEqual(self.scalar("SELECT duration_seconds FROM game_timers WHERE user_id = 1"), 7200)
        self.assertEqual(self.scalar("SELECT is_active FROM game_timers WHERE user_id = 2"), 1)

    def test_seasons_are_still_derived(self):
        self.assertEqual(self.scalar("SELECT season FROM game_timers WHERE user_id = 2"), 2026)
        self.assertEqual(self.scalar("SELECT season FROM users_achievements WHERE user_id = 1"), 2025)
