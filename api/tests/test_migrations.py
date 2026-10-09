"""Static guards for the Alembic history (no database needed).

Migrations are the riskiest part of the project: these tests fail on the mistakes
that are cheap to detect before anything touches a real database. They do not
replace running `alembic upgrade head` on an empty DB and on a copy of production.
"""
import ast
import re
import sys
import unittest
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent

# api/alembic/ (our migrations folder) would shadow the installed `alembic` package
# whenever api/ is on sys.path, which is exactly how the tests are run.
_saved_path = sys.path[:]
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != API_DIR]
try:
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
finally:
    sys.path[:] = _saved_path

VERSIONS_DIR = API_DIR / "alembic" / "versions"
# alembic_version.version_num is VARCHAR(32)
MAX_REVISION_LENGTH = 32
FILENAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.py$")


def load_script_directory() -> ScriptDirectory:
    config = AlembicConfig(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


class MigrationHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = load_script_directory()
        cls.revisions = list(cls.script.walk_revisions())  # newest first

    def test_single_head(self):
        self.assertEqual(len(self.script.get_heads()), 1, f"several heads: {self.script.get_heads()}")

    def test_history_is_linear(self):
        for rev in self.revisions:
            self.assertFalse(rev.is_merge_point, f"{rev.revision} merges branches")
            self.assertFalse(rev.is_branch_point, f"{rev.revision} starts a branch")
            self.assertFalse(rev.branch_labels, f"{rev.revision} uses branch labels")

    def test_single_root(self):
        self.assertEqual(len(self.script.get_bases()), 1)

    def test_revision_ids_fit_the_version_table(self):
        for rev in self.revisions:
            self.assertLessEqual(len(rev.revision), MAX_REVISION_LENGTH, rev.revision)

    def test_files_are_numbered_without_gaps_and_match_the_chain(self):
        files = sorted(p.name for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")
        numbers = []
        for name in files:
            match = FILENAME.match(name)
            self.assertIsNotNone(match, f"{name}: expected NNN_short_name.py")
            numbers.append(int(match.group(1)))
        self.assertEqual(numbers, list(range(len(files))), "numbers must be 000, 001, ... with no gaps or repeats")

        chain = [rev for rev in reversed(self.revisions)]  # oldest first
        for name, rev in zip(files, chain):
            self.assertTrue(
                Path(rev.path).name == name,
                f"file order and revision order disagree: {name} vs {Path(rev.path).name}",
            )
            self.assertTrue(rev.revision.startswith(name[:3] + "_"), f"{rev.revision} must start with {name[:3]}_")

    def test_every_migration_documents_and_defines_both_directions(self):
        for rev in self.revisions:
            tree = ast.parse(Path(rev.path).read_text(encoding="utf-8"))
            self.assertTrue(ast.get_docstring(tree), f"{rev.revision}: missing module docstring")
            functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
            self.assertIn("upgrade", functions, rev.revision)
            self.assertIn("downgrade", functions, rev.revision)


def load_migration(name: str):
    import importlib.util

    path = VERSIONS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"migration_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BaselineTests(unittest.TestCase):
    """000 lets an empty database walk the chain that was written for v1 backups."""

    @classmethod
    def setUpClass(cls):
        cls.baseline = load_migration("000_baseline_v1")

    def test_it_is_the_only_root_and_001_follows_it(self):
        script = load_script_directory()
        self.assertEqual(script.get_bases(), ["000_baseline_v1"])
        self.assertEqual(script.get_revision("001_add_rawg_id").down_revision, "000_baseline_v1")

    def test_it_never_drops_anything(self):
        with self.assertRaises(RuntimeError):
            self.baseline.downgrade()

    def test_every_table_is_created_only_if_missing(self):
        source = (VERSIONS_DIR / "000_baseline_v1.py").read_text(encoding="utf-8")
        self.assertIn("if table not in existing", source)
        self.assertNotIn("DROP ", source.upper().replace("DROPPING", ""))

    def test_it_creates_what_the_first_migrations_need(self):
        names = [table for table, _, _ in self.baseline.TABLES]
        self.assertEqual(len(names), len(set(names)))
        # 001 alters games, 003 reads time_entries and games_statistics, 005 renames the four
        # historical tables, 006-009 alter users, users_games and users_achievements
        needed = {
            "games", "users", "users_games", "users_achievements", "achievements", "platform_tags",
            "time_entries", "games_statistics", "time_entries_historical", "users_games_historical",
            "games_statistics_historical", "users_statistics_historical",
        }
        self.assertEqual(set(names), needed)


class PlatformSeedTests(unittest.TestCase):
    def test_default_platforms_have_unique_ids_that_fit_the_column(self):
        platforms = load_migration("015_seed_platforms").PLATFORMS
        ids = [id_ for id_, _ in platforms]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(0 < len(i) <= 255 for i in ids))
        self.assertIn("pc", ids)


class ForeignKeyMigrationTests(unittest.TestCase):
    def test_the_migration_and_the_models_declare_the_same_keys(self):
        from src.database import models

        migration = load_migration("016_foreign_keys")
        declared = {
            (fk.name, table.name, fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete)
            for table in models.Base.metadata.tables.values()
            for fk in table.foreign_keys
            if table.name not in ("user_settings", "password_resets", "game_scores", "users_wishlist", "audit_log", "challenges", "challenge_optouts")  # created with their key by 014, 017, 019, 021, 022 and 034
        }
        self.assertEqual(declared, set(migration.KEYS))

    def test_it_refuses_instead_of_fixing_and_says_where(self):
        source = (VERSIONS_DIR / "016_foreign_keys.py").read_text(encoding="utf-8")
        self.assertIn("nothing was changed", source)
        self.assertNotIn("DELETE FROM", source)
        self.assertNotIn("UPDATE ", source.replace("ON UPDATE", ""))


if __name__ == "__main__":
    unittest.main()
