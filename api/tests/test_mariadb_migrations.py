"""Migrations and schema rules checked on a real MariaDB (see tests/mariadb_db.py).

`test_migrations.py` only inspects the files; these run them. They cover steps 2, 3, 4 and 6 of the
verification checklist in docs/migrations.md (empty -> head, an older revision with data -> head,
re-run, downgrade and back) plus the rules that only MariaDB enforces. The checklist's step 3 with a
copy of the production backup stays manual: it needs real data.
"""
import ast
import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.database import models
from tests.mariadb_db import MariaDBTestCase
from tests.test_migrations import VERSIONS_DIR, load_script_directory

# Old enough to be a fixed point (applied migrations are immutable, so data seeded at this revision
# stays valid forever) and recent enough that every later migration upgrades real-looking tables.
SEEDED_REVISION = "016_foreign_keys"


def head_revision() -> str:
    return load_script_directory().get_current_head()


def head_downgrade_is_defined() -> bool:
    """Irreversible migrations (like 000) raise in downgrade() on purpose; there is nothing to test."""
    rev = load_script_directory().get_revision(head_revision())
    tree = ast.parse(Path(rev.path).read_text(encoding="utf-8"))
    downgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "downgrade")
    return not any(isinstance(n, ast.Raise) for n in ast.walk(downgrade))


class EmptyDatabaseToHeadTests(MariaDBTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate()

    def test_it_ends_at_the_single_head(self):
        self.assertEqual(self.current_revision(), head_revision())

    def test_running_it_again_changes_nothing(self):
        result = self.alembic("upgrade", "head")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current_revision(), head_revision())

    def test_every_table_and_column_of_the_models_exists(self):
        """A model column without a migration would only fail in production, at the first query."""
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        for table in models.Base.metadata.sorted_tables:
            self.assertIn(table.name, existing, f"table {table.name} has no migration")
            columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                self.assertIn(column.name, columns, f"{table.name}.{column.name} has no migration")

    def test_season_is_generated_by_the_database_from_the_date(self):
        # the three tables that derive it (rule 2 of AGENTS.md)
        for table, column in (("users_games", "season"), ("game_timers", "season"), ("users_achievements", "season")):
            extra = {c["name"]: c for c in inspect(self.engine).get_columns(table)}[column]
            self.assertIsNotNone(extra.get("computed"), f"{table}.{column} must be a generated column")


class DowngradeTests(MariaDBTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate()

    def test_one_step_down_and_up_again(self):
        if not head_downgrade_is_defined():
            self.skipTest("the newest migration is irreversible on purpose")
        down = self.alembic("downgrade", "-1")
        self.assertEqual(down.returncode, 0, down.stderr)
        self.assertNotEqual(self.current_revision(), head_revision())
        self.migrate()
        self.assertEqual(self.current_revision(), head_revision())


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

    def test_deleting_a_user_removes_their_settings(self):
        self.execute("INSERT INTO users (id, username, email) VALUES (51, 'cai', 'cai@example.com')")
        self.execute("INSERT INTO user_settings (user_id) VALUES (51)")
        self.execute("DELETE FROM users WHERE id = 51")
        self.assertEqual(self.execute("SELECT COUNT(*) FROM user_settings WHERE user_id = 51").scalar(), 0)


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
