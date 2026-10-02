import types
import unittest
from unittest import mock

import bcrypt

from src.crud import users
from src.database.database import engine

PASSWORD = "Str0ng!Passw0rd"


def hashed(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def db_with(user):
    db = mock.MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


class EnsureGodUserTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(users.config, "GOD_ADMIN_PASS", PASSWORD)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_missing_admin_is_created_with_the_configured_password(self):
        db = db_with(None)
        users.ensure_god_user(db)
        created = db.add.call_args.args[0]
        self.assertEqual((created.username, created.is_admin, created.is_active), ("admin", 1, 1))
        self.assertTrue(bcrypt.checkpw(PASSWORD.encode(), created.password.encode()))

    def test_the_same_password_keeps_its_hash_so_sessions_survive_a_restart(self):
        stored = hashed(PASSWORD)
        user = types.SimpleNamespace(name="x", password=stored, is_admin=0, is_active=0)
        users.ensure_god_user(db_with(user))
        self.assertEqual(user.password, stored)
        self.assertEqual((user.name, user.is_admin, user.is_active), ("Dios", 1, 1))

    def test_a_changed_password_is_restored(self):
        user = types.SimpleNamespace(name="Dios", password=hashed("Other!Passw0rd1"), is_admin=1, is_active=1)
        users.ensure_god_user(db_with(user))
        self.assertTrue(bcrypt.checkpw(PASSWORD.encode(), user.password.encode()))

    def test_an_unusable_stored_hash_is_replaced(self):
        for stored in (None, "", "not-a-hash"):
            user = types.SimpleNamespace(name="Dios", password=stored, is_admin=1, is_active=1)
            users.ensure_god_user(db_with(user))
            self.assertTrue(bcrypt.checkpw(PASSWORD.encode(), user.password.encode()), repr(stored))


class EngineTests(unittest.TestCase):
    def test_stale_connections_are_detected_and_recycled(self):
        self.assertTrue(engine.pool._pre_ping)
        self.assertLess(engine.pool._recycle, 8 * 3600)

    def test_the_pool_covers_every_worker_thread(self):
        # 40 request threads by default, plus the scheduler and the background checks
        self.assertGreaterEqual(engine.pool.size() + engine.pool._max_overflow, 40 + 10)


if __name__ == "__main__":
    unittest.main()
