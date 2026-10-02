"""Migrations that refuse to run on data that breaks what they are about to enforce (MariaDB required).

docs/migrations.md: a migration never rewrites data to make a constraint fit; it stops, says what is
wrong and leaves the database as it was, so that a person decides. For each refusal these tests check
the three things that matter: it fails and names the offending data, the database stays at the last
revision that was applied (with the schema untouched), and once the data is fixed running it again
converges to the head. The v1 database of tests/v1_fixture.py is the starting point; 007 and 009 are in
test_mariadb_v1_upgrade.py.
"""
from sqlalchemy import inspect, text

from tests import v1_fixture as fx
from tests.mariadb_db import MariaDBTestCase
from tests.test_mariadb_migrations import head_revision


class RefusalCase:
    """Mixin: one broken database, one refused upgrade, one fix. Subclasses fill in the class attributes."""

    prepare_until: str | None = None    # migrate this far before breaking the data (None: break the v1 data as it is)
    break_sql: tuple = ()               # statements that put the offending data in
    stays_at: str                       # the last revision that must have been applied
    mentions: tuple = ()                # what the message must say
    fix_sql: tuple = ()                 # what a person would do about it

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        if cls.prepare_until:
            cls.migrate(cls.prepare_until)
        with cls.engine.begin() as conn:
            for statement in cls.break_sql:
                conn.execute(text(statement))
        cls.schema_before = cls.schema_snapshot()
        cls.refused = cls.alembic("upgrade", "head")
        # what was left behind, captured now: the test that fixes the data and migrates on runs before the others
        # (unittest orders them by name) and changes this very database
        cls.revision_after = cls.current_revision()
        cls.schema_after = cls.schema_snapshot()
        cls.observed = cls.observe()

    @classmethod
    def observe(cls) -> dict:
        """Extra facts about the database right after the refusal, for a case's own assertions."""
        return {}

    def test_the_upgrade_fails_and_says_what_is_wrong(self):
        self.assertNotEqual(self.refused.returncode, 0)
        output = self.refused.stdout + self.refused.stderr
        for fragment in self.mentions:
            self.assertIn(fragment, output)

    def test_the_database_stays_at_the_last_applied_revision(self):
        self.assertEqual(self.revision_after, self.stays_at)

    def test_it_changes_nothing_in_the_step_that_refused(self):
        """The refusing migration checks before it changes anything, so nothing of its own may be there."""
        self.check_untouched()

    def check_untouched(self):
        """Extra assertions of a case about what the refusing migration must not have done (use `self.observed`)."""

    def test_after_the_data_is_fixed_it_runs_to_the_head(self):
        with self.engine.begin() as conn:
            for statement in self.fix_sql:
                conn.execute(text(statement))
        again = self.alembic("upgrade", "head")
        self.assertEqual(again.returncode, 0, again.stderr[-1500:])
        self.assertEqual(self.current_revision(), head_revision())


class SeasonDisagreesWithTheDateTests(RefusalCase, MariaDBTestCase):
    """008: `season` becomes derived from the date, so a row where they disagree has to be looked at first."""

    break_sql = ("UPDATE users_games SET season = 1999 WHERE id = (SELECT MIN(id) FROM (SELECT id FROM users_games) x)",)
    stays_at = "007_users_unique_email"
    mentions = ("users_games", "season differs", "YEAR(started_date)")
    fix_sql = ("UPDATE users_games SET season = YEAR(started_date)",)

    @classmethod
    def observe(cls):
        columns = {c["name"]: c for c in inspect(cls.engine).get_columns("users_games")}
        return {"season_is_generated": columns["season"].get("computed") is not None}

    def check_untouched(self):
        self.assertFalse(self.observed["season_is_generated"], "season must still be a plain column")


class AchievementSeasonDisagreesTests(RefusalCase, MariaDBTestCase):
    break_sql = ("UPDATE users_achievements SET season = 1999 WHERE id = (SELECT MIN(id) FROM (SELECT id FROM users_achievements) x)",)
    stays_at = "007_users_unique_email"
    mentions = ("users_achievements", "season differs")
    fix_sql = ("UPDATE users_achievements SET season = YEAR(`date`)",)


class DuplicateLibraryEntriesTests(RefusalCase, MariaDBTestCase):
    """008: a NULL platform may repeat in the old unique key, but not in the new one."""

    break_sql = (
        f"INSERT INTO users_games (user_id, game_id, started_date, season, platform) VALUES "
        f"(2, '{fx.DUNGEON}', '2025-06-01', 2025, NULL), (2, '{fx.DUNGEON}', '2025-07-01', 2025, NULL)",
    )
    stays_at = "007_users_unique_email"
    mentions = ("users_games", "several rows share", "(user, game, platform, season)")
    fix_sql = (f"DELETE FROM users_games WHERE user_id = 2 AND game_id = '{fx.DUNGEON}' AND started_date = '2025-07-01'",)


class RepeatedArchivedKeysTests(RefusalCase, MariaDBTestCase):
    """011: restoring the old library would create duplicates if the archive repeats a key."""

    break_sql = (
        f"INSERT INTO users_games_2024 (user_id, game_id, started_date, platform, season) VALUES "
        f"(3, '{fx.HOLLOW}', '2024-03-03', NULL, 2024), (3, '{fx.HOLLOW}', '2024-04-04', NULL, 2024)",
    )
    stays_at = "010_drop_clockify"
    mentions = ("_archived_users_games_2024", "repeats", "decide by hand")
    fix_sql = (f"DELETE FROM _archived_users_games_2024 WHERE user_id = 3 AND game_id = '{fx.HOLLOW}' AND started_date = '2024-04-04'",)

    @classmethod
    def observe(cls):
        with cls.engine.connect() as conn:
            return {"restored": conn.execute(text("SELECT COUNT(*) FROM users_games WHERE season IN (2023, 2024)")).scalar()}

    def check_untouched(self):
        self.assertEqual(self.observed["restored"], 0, "nothing may be restored before the check")


class OrphanReferencesTests(RefusalCase, MariaDBTestCase):
    """016: the foreign keys cannot be added while a row points at something that does not exist."""

    prepare_until = "015_seed_platforms"
    break_sql = (
        "INSERT INTO game_timers (user_id, game_id, start_time, end_time, duration_seconds, is_active) "
        "VALUES (1, 'a-game-that-never-existed', '2026-01-05 20:00:00', '2026-01-05 21:00:00', 3600, 0)",
        "UPDATE users_games SET platform = 'zx-spectrum' WHERE id = (SELECT MIN(id) FROM (SELECT id FROM users_games) x)",
    )
    stays_at = "015_seed_platforms"
    mentions = ("Cannot add the foreign keys", "nothing was changed", "game_timers.game_id", "a-game-that-never-existed",
                "users_games.platform", "zx-spectrum")
    fix_sql = (
        "DELETE FROM game_timers WHERE game_id = 'a-game-that-never-existed'",
        "UPDATE users_games SET platform = 'pc' WHERE platform = 'zx-spectrum'",
    )

    @classmethod
    def observe(cls):
        inspector = inspect(cls.engine)
        return {table: inspector.get_foreign_keys(table) for table in ("game_timers", "users_games")}

    def check_untouched(self):
        for table, keys in self.observed.items():
            self.assertEqual(keys, [], f"{table} must have no foreign key yet")
        self.assertEqual(self.schema_after, self.schema_before)

    def test_every_problem_is_reported_at_once_not_one_per_run(self):
        output = self.refused.stdout + self.refused.stderr
        self.assertIn("game_timers.game_id", output)
        self.assertIn("users_games.platform", output)


class EmptyStringIdentifierTests(RefusalCase, MariaDBTestCase):
    """016: an empty string where an id is expected is a reference to nothing, not a missing value."""

    prepare_until = "015_seed_platforms"
    break_sql = ("UPDATE game_timers SET platform = '' WHERE id = (SELECT MIN(id) FROM (SELECT id FROM game_timers) x)",)
    stays_at = "015_seed_platforms"
    mentions = ("game_timers.platform", "point at a platform_tags.id that does not exist", "''")
    fix_sql = ("UPDATE game_timers SET platform = NULL WHERE platform = ''",)

    def check_untouched(self):
        self.assertEqual(self.schema_after, self.schema_before)


class NullReferencesAreFineTests(MariaDBTestCase):
    """The counterpart: a nullable reference that is NULL (a session without a platform) is not an orphan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        cls.migrate("015_seed_platforms")
        with cls.engine.begin() as conn:
            conn.execute(text("UPDATE game_timers SET platform = NULL"))
        cls.result = cls.alembic("upgrade", "head")

    def test_the_foreign_keys_are_added(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-1500:])
        self.assertEqual(self.current_revision(), head_revision())
        referred = {fk["referred_table"] for fk in inspect(self.engine).get_foreign_keys("game_timers")}
        self.assertEqual(referred, {"users", "games", "platform_tags"})
