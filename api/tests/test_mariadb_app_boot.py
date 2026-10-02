"""The application starts and serves what the routers declare (MariaDB required).

The other API tests import the routers or call functions; none of them boots `src.main`, where the
routers are mounted under /api/v1, the docs are hidden and the database is seeded. A dependency that
changes how routes are handled would pass all of them and still leave the container unable to start.
This runs the real startup in a subprocess (tests/app_probe.py) against a freshly migrated database.
"""
import json

from sqlalchemy import text

from tests.app_routes import BASE, declared_routes
from tests.mariadb_db import MariaDBTestCase

# reachable without a token, and what they answer to an empty request
OPEN = {f"GET {BASE}/": 200, f"GET {BASE}/keepalive": 200}
OPEN_NEEDING_A_BODY = {f"POST {BASE}/token", f"POST {BASE}/auth/forgot-password", f"POST {BASE}/auth/reset-password"}
OPEN_WITH_A_PARAMETER = {f"GET {BASE}/utils/achievement-image/{{achievement}}"}


class AppBootTests(MariaDBTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migrate()
        cls.result = cls.python("tests/app_probe.py")
        lines = [line for line in cls.result.stdout.splitlines() if line.startswith("PROBE:")]
        cls.probe = json.loads(lines[-1][len("PROBE:"):]) if lines else None

    def test_it_starts(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-3000:])
        self.assertIsNotNone(self.probe, self.result.stderr[-3000:])

    def test_without_a_token_only_the_open_routes_answer(self):
        for route, code in self.probe["status"].items():
            with self.subTest(route=route):
                if route in OPEN:
                    self.assertEqual(code, OPEN[route])
                elif route in OPEN_NEEDING_A_BODY:
                    self.assertEqual(code, 422)
                elif route in OPEN_WITH_A_PARAMETER:
                    self.assertNotEqual(code, 401)
                else:
                    self.assertEqual(code, 401, "a protected route answers 401, 404 would mean it is not published")

    def test_every_declared_route_is_in_the_schema_and_nothing_else_is(self):
        declared = {f"{method} {path}" for method, path in declared_routes()}
        self.assertEqual(set(self.probe["schema"]), declared)

    def test_the_interactive_docs_are_hidden_by_default(self):
        self.assertEqual(self.probe["docs"], {path: 404 for path in self.probe["docs"]})

    def test_startup_seeded_the_database(self):
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).scalar(), 1)
            self.assertGreater(conn.execute(text("SELECT COUNT(*) FROM achievements")).scalar(), 0)
            self.assertGreater(conn.execute(text("SELECT COUNT(*) FROM app_settings")).scalar(), 0)
