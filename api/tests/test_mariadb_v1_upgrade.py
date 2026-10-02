"""A v1 database with data, taken to the head by the real migration chain (MariaDB required).

This is the road a v1 backup walks in production: import the dump (no `alembic_version`), start the
API, `alembic upgrade head` runs 000 to the latest. The data comes from tests/v1_fixture.py, which
is synthetic; what must hold afterwards is computed from the fixture's own rows. Only a copy of the
real backup can prove more than this, and that check stays manual (docs/migrations.md, step 3).
"""
from sqlalchemy import inspect, text

from tests import v1_fixture as fx
from tests.mariadb_db import MariaDBTestCase
from tests.test_mariadb_migrations import head_revision


class V1BackupToHeadTests(MariaDBTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.expected = fx.load(cls.engine)
        cls.migrate()

    def rows(self, sql, **params):
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).all()

    def scalar(self, sql, **params):
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()

    def test_it_reaches_the_head_and_a_second_run_changes_nothing(self):
        self.assertEqual(self.current_revision(), head_revision())
        again = self.alembic("upgrade", "head")
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_every_session_is_kept_and_no_played_time_is_lost(self):
        e = self.expected
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), e.timers)
        self.assertEqual(self.scalar("SELECT COALESCE(SUM(duration_seconds), 0) FROM game_timers"), e.timer_seconds)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers WHERE is_active = 1"), 0)

    def test_sessions_land_in_the_season_of_their_start(self):
        by_season = {s: n for s, n in self.rows("SELECT season, COUNT(*) FROM game_timers GROUP BY season")}
        self.assertEqual(by_season, self.expected.timers_by_season)

    def test_a_double_start_keeps_only_the_longest_session(self):
        rows = self.rows(
            "SELECT duration_seconds FROM game_timers WHERE user_id = 1 AND game_id = :g AND start_time = :s",
            g=fx.HOLLOW, s=self.expected.double_start_start,
        )
        self.assertEqual([r[0] for r in rows], [self.expected.double_start_kept_seconds])

    def test_sessions_of_an_unknown_project_get_a_placeholder_game_and_no_platform(self):
        name = self.scalar("SELECT name FROM games WHERE id = :g", g=fx.ORPHAN_PROJECT)
        self.assertEqual(name, f"Juego desconocido ({fx.ORPHAN_PROJECT})")
        platforms = self.rows("SELECT platform FROM game_timers WHERE game_id = :g", g=fx.ORPHAN_PROJECT)
        self.assertEqual(len(platforms), self.expected.orphan_sessions)
        self.assertTrue(all(p[0] is None for p in platforms))

    def test_the_platform_comes_back_from_the_library(self):
        platforms = {r[0] for r in self.rows(
            "SELECT DISTINCT platform FROM game_timers WHERE user_id = 1 AND game_id = :g AND season IN (2025, 2026)",
            g=fx.HOLLOW,
        )}
        self.assertEqual(platforms, {"pc"})

    def test_emails_are_normalised_and_other_user_data_survives(self):
        emails = dict(self.rows("SELECT username, email FROM users"))
        self.assertEqual(emails, {"ana": "ana@example.com", "bea": "bea@example.com", "cai": None, "dani": "dani@example.com"})
        self.assertEqual(self.scalar("SELECT telegram_id FROM users WHERE username = 'bea'"), 1002)
        self.assertEqual(self.scalar("SELECT is_admin FROM users WHERE username = 'ana'"), 1)

    def test_the_clockify_and_derived_leftovers_are_gone(self):
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        for gone in ("logs", "request_sync", "other_tags", "core_notifications", "users_statistics", "games_statistics"):
            self.assertNotIn(gone, tables, gone)
        user_columns = {c["name"] for c in inspector.get_columns("users")}
        self.assertFalse({"clockify_id", "clockify_key"} & user_columns)
        library_columns = {c["name"] for c in inspector.get_columns("users_games")}
        self.assertNotIn("played_time", library_columns)
        self.assertIn("completion_time", library_columns)

    def test_what_held_data_is_archived_not_dropped(self):
        tables = set(inspect(self.engine).get_table_names())
        self.assertIn("_archived_time_entries", tables)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM _archived_time_entries"), self.expected.archived_time_entries)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM _archived_users_games_2024"), len(fx.LIBRARY_2024))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM _archived_users_games_historical"), len(fx.LIBRARY_HISTORICAL))

    def test_the_old_library_returns_only_what_it_should(self):
        by_season = {s: n for s, n in self.rows("SELECT season, COUNT(*) FROM users_games GROUP BY season")}
        self.assertEqual(by_season.get(2023), fx.RESTORED_2023)
        self.assertEqual(by_season.get(2024), fx.RESTORED_2024)
        self.assertEqual(by_season.get(2025), 3)
        self.assertEqual(by_season.get(2026), 2)
        # skipped on purpose: gone user, gone game, the 2025-dated row of the 2024 archive and the 2024 snapshot
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u", u=fx.GONE_USER), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE game_id = :g", g=fx.GONE_GAME), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = 4 AND game_id = :g", g=fx.PORTAL), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = 2 AND game_id = :g", g=fx.ROCKET), 0)

    def test_library_facts_are_copied_verbatim(self):
        row = self.rows(
            "SELECT completed, completed_date, score, completion_time FROM users_games "
            "WHERE user_id = 1 AND game_id = :g AND season = 2025", g=fx.HOLLOW,
        )[0]
        self.assertEqual((row[0], str(row[1]), row[2], row[3]), (1, "2025-03-01", 9.0, 36000))
        undated = self.rows("SELECT completed, completed_date FROM users_games WHERE user_id = 2 AND season = 2024")[0]
        self.assertEqual((undated[0], undated[1]), (1, None))

    def test_achievements_survive_with_a_derived_season(self):
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM achievements"), len(fx.ACHIEVEMENTS))
        seasons = sorted(r[0] for r in self.rows("SELECT season FROM users_achievements"))
        self.assertEqual(seasons, sorted(a[4] for a in fx.USERS_ACHIEVEMENTS))

    def test_the_foreign_keys_of_the_current_schema_are_in_place(self):
        referred = {fk["referred_table"] for fk in inspect(self.engine).get_foreign_keys("game_timers")}
        self.assertEqual(referred, {"users", "games", "platform_tags"})


class RefusalChecks:
    """A migration that cannot do its job safely stops and says why; it never rewrites data to fit."""

    broken_sql: str
    stops_before: str
    mentions: str

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        with cls.engine.begin() as conn:
            conn.execute(text(cls.broken_sql))
        cls.result = cls.alembic("upgrade", "head")

    def test_the_upgrade_fails_and_names_the_offending_value(self):
        self.assertNotEqual(self.result.returncode, 0)
        self.assertIn(self.mentions, self.result.stdout + self.result.stderr)

    def test_the_database_stays_at_the_last_good_revision(self):
        self.assertEqual(self.current_revision(), self.stops_before)


class TwoAccountsShareAnEmailTests(RefusalChecks, MariaDBTestCase):
    broken_sql = "UPDATE users SET email = 'ANA@example.com' WHERE username = 'bea'"
    stops_before = "006_backfill_timer_platform"
    mentions = "ana@example.com"


class TwoAccountsShareATelegramIdTests(RefusalChecks, MariaDBTestCase):
    broken_sql = "UPDATE users SET telegram_id = 1001 WHERE username = 'bea'"
    stops_before = "008_season_generated"
    mentions = "1001"
