"""Which checks CI runs for a change (`.github/scripts/ci_scope.py`). Skipping a check is only safe if what a test reads
from outside its own directory is listed: these tests pin that, so a new cross-directory read cannot be forgotten."""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ci_scope", ROOT / ".github" / "scripts" / "ci_scope.py")
ci_scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_scope)


def run(*paths):
    checks, services = ci_scope.scope(paths)
    return checks, services


class ScopeTests(unittest.TestCase):
    def test_documentation_and_project_files_run_nothing(self):
        for path in ("docs/features.md", "README.md", "CONTRIBUTING.md", "AGENTS.md", "LICENSE", ".gitignore",
                     "design/laViciacionLogo.jpg", ".github/pull_request_template.md", ".github/dependabot.yml"):
            self.assertEqual(run(path), (set(), set()), path)

    def test_the_front_runs_its_tests_and_the_api_test_that_reads_its_sources(self):
        self.assertEqual(run("front/js/pages/home/history.js"), ({"front-tests", "api-tests"}, {"front"}))
        self.assertEqual(run("front/css/home.css"), ({"front-tests"}, {"front"}))
        self.assertEqual(run("front/tests/modal.dom.test.js"), ({"front-tests"}, {"front"}))
        self.assertEqual(run("front/package-lock.json"), ({"front-tests"}, {"front"}))
        self.assertEqual(run("front/Dockerfile"), ({"front-tests", "api-tests"}, {"front"}))

    def test_the_api_runs_its_tests_with_and_without_a_database(self):
        self.assertEqual(run("api/src/crud/users.py"), ({"api-tests", "mariadb"}, {"api"}))

    def test_the_migration_tests_run_only_when_something_they_depend_on_changes(self):
        everything_api = ({"api-tests", "mariadb", "mariadb-migrations"}, {"api"})
        for path in ("api/alembic/versions/018_x.py", "api/alembic/env.py", "api/alembic.ini", "api/entrypoint.sh",
                     "api/src/database/models.py", "api/src/config.py", "api/requirements.txt",
                     "api/tests/mariadb_db.py", "api/tests/v1_fixture.py", "api/tests/test_mariadb_migration_chain.py",
                     "api/tests/test_mariadb_migrations.py"):
            self.assertEqual(run(path), everything_api, path)
        for path in ("api/src/crud/users.py", "api/src/routers/games.py", "api/src/utils/ai.py",
                     "api/tests/test_mariadb_api_users.py", "api/tests/test_wishlist.py", "api/Dockerfile"):
            self.assertEqual(run(path), ({"api-tests", "mariadb"}, {"api"}), path)

    def test_the_bot_source_is_also_read_by_the_api_tests_but_its_tests_are_not(self):
        self.assertEqual(run("bot/src/routes/my_routes.py"), ({"bot-tests", "api-tests", "mariadb"}, {"bot"}))
        self.assertEqual(run("bot/tests/test_gate.py"), ({"bot-tests"}, {"bot"}))

    def test_root_files_the_tests_read(self):
        self.assertEqual(run(".env.template"), ({"api-tests"}, set()))
        self.assertEqual(run("docker-compose.yml"), ({"api-tests", "mariadb", "mariadb-migrations"}, set()))  # the MariaDB version
        self.assertEqual(run("docker-compose.dev.yml"), ({"api-tests"}, set()))

    def test_anything_unclassified_runs_everything(self):
        everything = (set(ci_scope.ALL_CHECKS), set(ci_scope.ALL_SERVICES))
        for path in (".github/workflows/checks.yml", ".github/scripts/ci_scope.py", "newdir/file.txt", "Makefile", "db/init/x.sql"):
            self.assertEqual(run(path), everything, path)

    def test_one_unclassified_file_among_inert_ones_runs_everything(self):
        self.assertEqual(run("docs/a.md", "Makefile")[0], set(ci_scope.ALL_CHECKS))

    def test_a_mixed_change_runs_the_union(self):
        self.assertEqual(run("docs/a.md", "front/css/a.css", "bot/tests/t.py"), ({"front-tests", "bot-tests"}, {"front", "bot"}))

    def test_output_format(self):
        self.assertEqual(ci_scope.render({"front-tests"}, {"front"}), 'scope=front-tests\nbuild_services=["front"]\n')
        self.assertEqual(ci_scope.render(set(), set()), "scope=none\nbuild_services=[]\n")
        self.assertEqual(ci_scope.render(set(ci_scope.ALL_CHECKS), set(ci_scope.ALL_SERVICES)), 'scope=all\nbuild_services=["api", "front", "bot"]\n')
        self.assertEqual(ci_scope.render({"mariadb", "mariadb-migrations"}, {"api"}), 'scope=mariadb,mariadb-migrations\nbuild_services=["api"]\n')


class WhatTheTestsReadTests(unittest.TestCase):
    """The reverse check: a test that starts reading another directory must be added to ci_scope.py."""

    def test_api_tests_only_read_the_directories_the_scope_lists(self):
        read = set()
        for file in (ROOT / "api" / "tests").glob("test_*.py"):
            text = file.read_text(encoding="utf-8")
            for match in re.finditer(r'parents\[2\]\s*/\s*"(\w+)"', text):
                read.add(match.group(1))
            if "ROOT /" in text or "ROOT.glob" in text:
                read.add("<root>")
        # front/js (test_front_api_paths), bot/src (test_mariadb_bot_contract) and files of the repository root
        # (.env.template, docker-compose*.yml, */Dockerfile) are the reads ci_scope.py knows about
        self.assertEqual(read, {"front", "bot", "<root>"})


class MariaDBSetsTests(unittest.TestCase):
    """The MariaDB job is split by file name (mariadb-tests.yml): `test_mariadb_migration*.py` are the migration set,
    the rest the routes set. A test that runs alembic must be in the first, or the second would get slow and the
    first would not run when it should."""

    TESTS = ROOT / "api" / "tests"
    ALEMBIC_OUTSIDE_THE_SET = {"test_mariadb_app_boot.py"}  # one migration of its own to start the app

    def test_the_migration_set_is_the_four_files_that_exercise_the_chain(self):
        found = {f.name for f in self.TESTS.glob("test_mariadb_migration*.py")}
        self.assertEqual(found, {"test_mariadb_migration_chain.py", "test_mariadb_migration_refusals.py",
                                 "test_mariadb_migration_v1_upgrade.py", "test_mariadb_migrations.py"})

    def test_no_other_mariadb_test_runs_alembic_over_and_over(self):
        for file in self.TESTS.glob("test_mariadb_*.py"):
            if file.name.startswith("test_mariadb_migration"):
                continue
            text = file.read_text(encoding="utf-8")
            if file.name in self.ALEMBIC_OUTSIDE_THE_SET:
                self.assertEqual(text.count(".alembic("), 0, file.name)
                self.assertLessEqual(text.count(".migrate("), 1, file.name)
            else:
                self.assertNotIn(".alembic(", text, f"{file.name} runs alembic: name it test_mariadb_migration_*.py")
                self.assertNotIn(".migrate(", text, f"{file.name} migrates: name it test_mariadb_migration_*.py")


if __name__ == "__main__":
    unittest.main()
