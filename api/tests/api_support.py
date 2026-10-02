"""The real routers on a migrated MariaDB, for tests that make HTTP requests (MariaDB required).

`ApiTestCase` gives a test:

- a database that is migrated once per run and emptied before every test (so tests do not depend on each
  other, and the 19 migrations are not replayed for every class);
- the routers of `src/routers` mounted under /api/v1 exactly as `src/main.py` mounts them, without the
  startup work of main.py (the boot test covers that), and `get_db` pointing at the test database;
- users, games and tokens built the way the application builds them (`self.user`, `self.game`,
  `self.headers`), so a test reads as the request it makes;
- the work the application does *after* answering (announcements, push, AI) replaced by recorders, so
  nothing reaches the network and a test can still check that the right follow-up was scheduled.
"""
import atexit
import datetime
from datetime import timedelta
from unittest import mock

import bcrypt
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from src import auth
from src.crud.achievements import Achievements
from src.database import database, models
from src.routers import basic
from src.utils import actions, my_utils, settings
from tests import mariadb_db
from tests.app_routes import BASE, ROUTERS
from tests.mariadb_db import MariaDBTestCase

PASSWORD = "Sup3r-secret!pw"  # meets the password rules (12-24 characters, upper, lower, digit, symbol)

# what every test starts without: the rows tests create. platform_tags (seeded by migration 015) stays, as in a real
# database; the achievements catalogue is rebuilt from the code for every test, because tests may edit a title or
# upload an image and the next one must not see it.
DATA_TABLES = (
    "game_timers", "users_achievements", "achievements", "users_games", "push_subscriptions", "password_resets",
    "user_settings", "app_settings", "job_runs", "games", "users",
)

# the follow-ups the routers schedule with BackgroundTasks, replaced by recorders
BACKGROUND = ("after_timer_start", "after_timer_stop", "after_session_change", "after_completion")

_shared: dict = {}


def _drop_shared_database() -> None:
    if _shared.get("engine") is not None:
        _shared["engine"].dispose()
        with _shared["admin"].connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{_shared['name']}`"))
        _shared["admin"].dispose()
    if "bind" in _shared:
        database.SessionLocal.configure(bind=_shared["bind"])


def build_app() -> FastAPI:
    app = FastAPI()
    api = APIRouter(prefix=BASE)
    for module in ROUTERS:
        api.include_router(module.router)
    app.include_router(api)
    return app


class ApiTestCase(MariaDBTestCase):
    """Subclass it, then call `self.api(...)`. See the module docstring."""

    @classmethod
    def setUpClass(cls):
        if "engine" not in _shared:
            super().setUpClass()  # skips (or fails in CI) without a server; creates the scratch database
            cls.migrate()
            _shared.update(engine=cls.engine, admin=cls._admin, name=cls.db_name, bind=database.SessionLocal.kw["bind"])
            database.SessionLocal.configure(bind=cls.engine)
            atexit.register(_drop_shared_database)
        else:
            cls.engine, cls._admin, cls.db_name = _shared["engine"], _shared["admin"], _shared["name"]
        cls.app = build_app()
        cls.app.dependency_overrides[auth.get_db] = cls._db_dependency

    @classmethod
    def tearDownClass(cls):
        """The database outlives the class: it is dropped once, when the run ends."""

    @classmethod
    def _db_dependency(cls):
        db = database.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def setUp(self):
        with self.engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in DATA_TABLES:
                conn.execute(text(f"DELETE FROM `{table}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        with database.SessionLocal() as db:
            Achievements().populate_achievements(db)
        for limiter in (
            basic.LOGIN_BY_ACCOUNT, basic.LOGIN_BY_CLIENT, basic.RECOVERY_BY_ACCOUNT,
            basic.RECOVERY_BY_CLIENT, basic.RESET_LINK_FAILS,
        ):
            limiter._failures.clear()
        settings._cache.clear()  # settings are cached for a few seconds in the process
        self.background = {}
        self.real_actions = {name: getattr(actions, name) for name in BACKGROUND}  # for tests of the work itself
        for name in BACKGROUND:
            patcher = mock.patch.object(actions, name)
            self.background[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self._forbid_the_network()
        self.client = TestClient(self.app)

    def _forbid_the_network(self):
        """A test never talks to RAWG or HowLongToBeat, whatever the developer's .env says (Config reads it:
        a real RAWG key there would turn a test into a real request). A test that wants them replaces these."""

        async def no_network(url, params, timeout):
            raise AssertionError(f"a test tried to reach {url}")

        class NoHowLongToBeat:
            async def async_search(self, name):
                return []

        for patcher in (
            mock.patch.object(type(my_utils.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=""),
            mock.patch.object(my_utils, "_http_get", new=no_network),
            mock.patch.object(my_utils, "HowLongToBeat", new=NoHowLongToBeat),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    # --- requests

    def api(self, method: str, path: str, *, as_user: str | None = None, **kwargs):
        """One request to /api/v1<path>, authenticated as `as_user` (a username) when given."""
        headers = {**self.headers(as_user), **kwargs.pop("headers", {})} if as_user else kwargs.pop("headers", {})
        return self.client.request(method, f"{BASE}{path}", headers=headers, **kwargs)

    def headers(self, username: str) -> dict:
        with database.SessionLocal() as db:
            user = db.query(models.User).filter_by(username=username).one()
            token = auth.create_access_token(
                {"id": user.id, "username": user.username, "pwv": auth.password_fingerprint(user)}, timedelta(minutes=30)
            )
        return {"Authorization": f"Bearer {token}"}

    # --- data

    def user(self, username: str, *, admin: bool = False, active: bool = True, email: str | None = None,
             telegram_id: int | None = None, password: str = PASSWORD) -> int:
        """Creates a user and returns their id."""
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()  # cheap: tests make many
        with database.SessionLocal() as db:
            row = models.User(
                username=username, name=username.capitalize(), password=hashed, is_admin=int(admin),
                is_active=int(active), email=email if email is not None else f"{username}@example.com",
                telegram_id=telegram_id,
            )
            db.add(row)
            db.commit()
            return row.id

    def game(self, game_id: str, name: str | None = None, **fields) -> str:
        with database.SessionLocal() as db:
            db.add(models.Game(id=game_id, name=name or game_id.replace("-", " ").title(), **fields))
            db.commit()
        return game_id

    def session(self, user_id: int, game_id: str, start: datetime.datetime, minutes: int, platform: str | None = "pc") -> int:
        """A finished session, written straight to the table."""
        end = start + timedelta(minutes=minutes)
        with database.SessionLocal() as db:
            row = models.GameTimer(
                user_id=user_id, game_id=game_id, start_time=start, end_time=end,
                duration_seconds=minutes * 60, platform=platform, is_active=False,
            )
            db.add(row)
            db.commit()
            return row.id

    def library_entry(self, user_id: int, game_id: str, started: datetime.date, platform: str | None = "pc", **fields) -> int:
        with database.SessionLocal() as db:
            row = models.UserGame(user_id=user_id, game_id=game_id, started_date=started, platform=platform, **fields)
            db.add(row)
            db.commit()
            return row.id

    def set_settings(self, **values) -> None:
        """Stores admin settings (`self.set_settings(**{"telegram.token": "..."})`) and drops the in-process cache."""
        with database.SessionLocal() as db:
            settings.set_values(db, values)
        settings._cache.clear()

    def rows(self, sql: str, **params) -> list:
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).all()

    def scalar(self, sql: str, **params):
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()
