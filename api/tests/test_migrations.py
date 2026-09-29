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
        self.assertEqual(numbers, list(range(1, len(files) + 1)), "numbers must be 001, 002, ... with no gaps or repeats")

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


if __name__ == "__main__":
    unittest.main()
