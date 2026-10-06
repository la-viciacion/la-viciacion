"""Every migration of the chain, one by one, on a real MariaDB (see tests/mariadb_db.py).

`test_mariadb_migrations.py` and `test_mariadb_v1_upgrade.py` check the ends of the road (empty or v1
to head). These check each step: that it applies on data, that running it again changes nothing,
that it can be undone, that both roads end in the same schema and that the schema is what the models
say. They automate steps 2, 4, 6 and 7 of the checklist in docs/migrations.md for all migrations.
"""
import unittest

from sqlalchemy import text
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from src.database import models
from tests import v1_fixture as fx
from tests.mariadb_db import MariaDBTestCase
from tests.test_mariadb_migrations import head_revision
from tests.test_migrations import load_script_directory


def revisions() -> list[str]:
    """Oldest first."""
    return [r.revision for r in reversed(list(load_script_directory().walk_revisions()))]


# 001-005 were written before migrations had to be re-runnable (001 adds a column, 002 creates a
# table, 004 and 005 rename tables: a second run fails). They are applied everywhere and immutable,
# so the rule starts after them; every newer migration has to converge when run again.
LAST_REVISION_THAT_IS_NOT_RERUNNABLE = "005_prune_dead_tables"

# Downgrades that fail on MariaDB, with the reason. They are applied and immutable; the production
# way back is the pre-deploy backup (docs/deployment.md), not downgrade.
KNOWN_BROKEN_DOWNGRADES = {
    "008_season_generated": "ALTER TABLE ... MODIFY on a generated column is unsupported (error 1907)",
}


class EveryStepAppliesOnDataTests(MariaDBTestCase):
    """The v1 database goes up one revision at a time; a step that is re-run must change nothing."""

    results: dict

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        cls.results = {}
        ordered = revisions()
        rerunnable = ordered[ordered.index(LAST_REVISION_THAT_IS_NOT_RERUNNABLE) + 1:]
        previous = None
        for rev in ordered:
            up = cls.alembic("upgrade", rev)
            result = {"upgrade": up}
            if up.returncode == 0 and rev in rerunnable:
                before = (cls.schema_snapshot(), cls.data_snapshot())
                cls.alembic("stamp", previous)  # pretend this revision was interrupted before it was recorded
                again = cls.alembic("upgrade", rev)
                result["rerun"] = again
                result["same"] = before == (cls.schema_snapshot(), cls.data_snapshot()) if again.returncode == 0 else None
                cls.alembic("stamp", rev)  # whatever the second run did, carry on from the recorded revision
            cls.results[rev] = result
            if up.returncode != 0:
                break
            previous = rev

    def test_every_migration_applies(self):
        for rev in revisions():
            with self.subTest(revision=rev):
                self.assertIn(rev, self.results, "an earlier migration failed")
                up = self.results[rev]["upgrade"]
                self.assertEqual(up.returncode, 0, up.stderr[-2000:])

    def test_every_newer_migration_converges_when_run_again(self):
        ordered = revisions()
        for rev in ordered[ordered.index(LAST_REVISION_THAT_IS_NOT_RERUNNABLE) + 1:]:
            with self.subTest(revision=rev):
                again = self.results[rev]["rerun"]
                self.assertEqual(again.returncode, 0, again.stderr[-2000:])
                self.assertTrue(self.results[rev]["same"], f"{rev} changed the schema or the data on a second run")

    def test_the_old_exceptions_are_still_exactly_the_old_ones(self):
        """Keeps the exception list honest: it may only shrink, never grow with new migrations."""
        ordered = revisions()
        newer = ordered[ordered.index(LAST_REVISION_THAT_IS_NOT_RERUNNABLE) + 1:]
        self.assertTrue(newer, "no migration after the cut-off")
        self.assertEqual(ordered[: len(ordered) - len(newer)][-1], LAST_REVISION_THAT_IS_NOT_RERUNNABLE)


class DowngradeTests(MariaDBTestCase):
    """Walks back from the head and up again; the schema must come back as it was.

    Data is not compared: several downgrades recreate dropped tables empty, on purpose.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        cls.migrate()
        cls.schema_at_head = cls.schema_snapshot()
        cls.steps: dict[str, object] = {}
        cls.blocked_at: str | None = None
        for rev in reversed(revisions()[1:]):  # 000 is irreversible on purpose
            result = cls.alembic("downgrade", "-1")
            cls.steps[rev] = result
            if result.returncode != 0:
                cls.blocked_at = rev
                break

    def test_every_downgrade_runs_or_is_a_known_limitation(self):
        for rev, result in self.steps.items():
            if result.returncode != 0:
                with self.subTest(revision=rev):
                    self.assertIn(rev, KNOWN_BROKEN_DOWNGRADES, result.stderr[-2000:])

    def test_the_known_limitations_are_still_real(self):
        """Fails the day a listed downgrade works, so the list gets cleaned up."""
        for rev in KNOWN_BROKEN_DOWNGRADES:
            if rev in self.steps:
                with self.subTest(revision=rev):
                    self.assertNotEqual(self.steps[rev].returncode, 0, f"{rev} downgrades now: remove it from the list")

    def test_it_goes_up_again_to_the_same_schema(self):
        if self.blocked_at is not None:
            # a failed downgrade leaves the database at that revision, untouched (it fails on its first statement)
            self.assertEqual(self.current_revision(), self.blocked_at)
        self.migrate()
        self.assertEqual(self.current_revision(), head_revision())
        self.assertEqual(self.schema_snapshot(), self.schema_at_head)


class DowngradeBelowTheKnownLimitationsTests(MariaDBTestCase):
    """The same walk for the revisions that lie under a broken downgrade, starting from the one just below."""

    @classmethod
    def setUpClass(cls):
        broken = [r for r in revisions() if r in KNOWN_BROKEN_DOWNGRADES]
        if not broken:
            raise unittest.SkipTest("no downgrade is broken: the walk from the head already covered everything")
        super().setUpClass()
        ordered = revisions()
        cls.start = ordered[ordered.index(broken[0]) - 1]
        fx.load(cls.engine)
        cls.migrate(cls.start)
        cls.schema_at_start = cls.schema_snapshot()
        cls.steps = {}
        for rev in reversed(ordered[1: ordered.index(cls.start) + 1]):
            cls.steps[rev] = cls.alembic("downgrade", "-1")
            if cls.steps[rev].returncode != 0:
                break

    def test_every_older_downgrade_runs(self):
        for rev, result in self.steps.items():
            with self.subTest(revision=rev):
                self.assertEqual(result.returncode, 0, result.stderr[-2000:])

    def test_it_goes_up_again_to_the_same_schema(self):
        self.migrate(self.start)
        self.assertEqual(self.schema_snapshot(), self.schema_at_start)


class BothRoadsEndInTheSameSchemaTests(MariaDBTestCase):
    """An empty database and a v1 backup must not end up with different schemas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fx.load(cls.engine)
        cls.migrate()
        # a second scratch database, created and dropped by its own class-level hooks
        cls.empty = type("EmptyRoad", (MariaDBTestCase,), {})
        cls.empty.setUpClass()
        cls.empty.migrate()

    @classmethod
    def tearDownClass(cls):
        cls.empty.tearDownClass()
        super().tearDownClass()

    @staticmethod
    def active(snapshot: dict) -> dict:
        # the v1 road archives more tables (users_games_2024, time_entries_legacy) than a new database
        # ever had, by design: only the active schema has to match
        return {t: ddl for t, ddl in snapshot.items() if not t.startswith("_archived_")}

    def test_same_tables_and_same_definitions(self):
        v1, empty = self.active(self.schema_snapshot()), self.active(self.empty.schema_snapshot())
        self.assertEqual(set(v1), set(empty))
        for table in v1:
            with self.subTest(table=table):
                self.assertEqual(v1[table], empty[table])

    def test_the_new_database_starts_without_rows_in_the_tables_that_hold_user_data(self):
        with self.empty.engine.connect() as conn:
            for table in ("users", "games", "game_timers", "users_games", "users_achievements"):
                with self.subTest(table=table):
                    self.assertEqual(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar(), 0)


class ModelParityTests(MariaDBTestCase):
    """`alembic check`, in code: the migrated schema must match the models, apart from the known noise."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate()

    @staticmethod
    def unexpected(operations) -> list:
        flat = []
        for op in operations:
            flat.extend(op if isinstance(op, list) else [op])
        left = []
        for op in flat:
            kind = op[0]
            if kind == "remove_table" and op[1].name.startswith("_archived_"):
                continue  # the archives migration 005 leaves behind have no model on purpose
            if kind == "remove_index" and (op[1].table.name.startswith("_archived_") or op[1].name.startswith("ix_game_timers_")):
                continue  # their indexes; and the game_timers indexes the migrations create but the model does not declare
            if kind == "modify_type" and (op[2], op[3]) in {("achievements", "image"), ("users", "avatar")}:
                continue  # LONGBLOB in the database, LargeBinary in the model: the same thing
            if kind == "modify_default" and (op[2], op[3]) == ("game_timers", "is_active"):
                continue  # server default 1 in the database, a Python-side default in the model
            left.append(op)
        return left

    def test_the_models_and_the_migrated_schema_agree(self):
        with self.engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
            diff = compare_metadata(context, models.Base.metadata)
        left = self.unexpected(diff)
        self.assertEqual(left, [], "models and migrations disagree (add a migration, or fix the model):\n" + "\n".join(map(str, left)))
