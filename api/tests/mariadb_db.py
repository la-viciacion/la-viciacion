"""A throwaway database on a real MariaDB server, for the tests that SQLite cannot stand in for
(migrations, generated columns, CHECK/UNIQUE/foreign-key rules).

The server comes from TEST_MARIADB_URL, a SQLAlchemy URL of an account that may create databases,
e.g. `mysql+pymysql://root:testpw@127.0.0.1:3399` (see docs/development.md). Without it the tests
are skipped, so `unittest discover` keeps working with no Docker around; CI sets
REQUIRE_MARIADB_TESTS=1 so a missing server there is a failure, never a silent skip.

Never point it at a server that holds real data: every test creates its own database
(`lavi_test_<random>`) and drops it at the end, but it is still the server's admin account.
"""
import os
import re
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from tests import clock

API_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("TEST_MARIADB_URL", "").strip()


def pin_server_clock(dbapi_connection, connection_record, connection_proxy):
    """The columns that default to CURRENT_TIMESTAMP (`updated_at`, `added_at`) are filled by the server's clock, which the
    pinned clock of the tests (tests/clock.py) does not reach: without this a rating made "now" would be dated months
    after the sessions the same test made "5 hours ago". Not on the real server, only for connections of the tests."""
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SET SESSION timestamp = UNIX_TIMESTAMP(%s)", (clock.now().strftime("%Y-%m-%d %H:%M:%S"),))


class MariaDBTestCase(unittest.TestCase):
    """Skips (or fails in CI) without a server; otherwise gives the class its own empty database."""

    db_name: str
    engine = None

    @classmethod
    def setUpClass(cls):
        if not ADMIN_URL:
            if os.environ.get("REQUIRE_MARIADB_TESTS"):
                raise AssertionError("REQUIRE_MARIADB_TESTS is set but TEST_MARIADB_URL is not")
            raise unittest.SkipTest("TEST_MARIADB_URL is not set (no MariaDB to test against)")
        cls.db_name = f"lavi_test_{uuid.uuid4().hex[:12]}"
        cls._admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
        with cls._admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE `{cls.db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        cls.engine = create_engine(make_url(ADMIN_URL).set(database=cls.db_name))
        event.listen(cls.engine, "checkout", pin_server_clock)

    @classmethod
    def tearDownClass(cls):
        if cls.engine is not None:
            cls.engine.dispose()
            with cls._admin.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS `{cls.db_name}`"))
            cls._admin.dispose()

    @classmethod
    def app_env(cls) -> dict[str, str]:
        """The environment of the API (and of alembic, whose env.py builds its URL from the same variables)
        pointing at this class's database. The other settings are dummies: nothing reaches out to a service."""
        url = make_url(ADMIN_URL)
        env = {
            **os.environ,
            "MARIADB_HOST": f"{url.host}:{url.port}" if url.port else url.host,
            "MARIADB_DATABASE": cls.db_name,
            "MARIADB_USER": url.username,
            "MARIADB_PASSWORD": url.password or "",
            "GOD_ADMIN_PASS": "ci",
            "SECRET_KEY": "ci-secret",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
            "CORS_ORIGINS": "[]",
            "SENTRY_URL_API": "",
            "ENVIRONMENT": "test",
            "API_LOG_LEVEL": "INFO",
        }
        env.pop("API_DOCS_ENABLED", None)  # the default (hidden docs) is what production runs
        return env

    @classmethod
    def alembic(cls, *args: str) -> subprocess.CompletedProcess:
        """Runs the alembic CLI against this class's database, as entrypoint.sh does in production."""
        return cls.python("-m", "alembic", *args)

    @classmethod
    def python(cls, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, *args],
            cwd=API_DIR, env={**cls.app_env(), "PYTHONPATH": str(API_DIR)}, capture_output=True, text=True, timeout=300,
        )

    @classmethod
    def migrate(cls, target: str = "head") -> None:
        result = cls.alembic("upgrade", target)
        if result.returncode != 0:
            raise AssertionError(f"alembic upgrade {target} failed:\n{result.stdout}\n{result.stderr}")

    @classmethod
    def session(cls):
        return sessionmaker(bind=cls.engine, autoflush=False)()

    @classmethod
    def current_revision(cls) -> str | None:
        with cls.engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

    @classmethod
    def schema_snapshot(cls) -> dict[str, str]:
        """table -> its CREATE TABLE, without the AUTO_INCREMENT counter (which only says how many rows existed)."""
        with cls.engine.connect() as conn:
            tables = [t for (t,) in conn.execute(text("SHOW TABLES")) if t != "alembic_version"]
            return {
                t: re.sub(r" AUTO_INCREMENT=\d+", "", conn.execute(text(f"SHOW CREATE TABLE `{t}`")).all()[0][1])
                for t in tables
            }

    @classmethod
    def data_snapshot(cls) -> dict[str, tuple]:
        """table -> (row count, checksum): equal snapshots mean a migration left the data as it was."""
        with cls.engine.connect() as conn:
            tables = [t for (t,) in conn.execute(text("SHOW TABLES")) if t != "alembic_version"]
            return {
                t: (
                    conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar(),
                    conn.execute(text(f"CHECKSUM TABLE `{t}`")).all()[0][1],
                )
                for t in tables
            }
