import unittest

from src import auth
from src.routers import basic, games, manage, push, statistics, timers, users, utils


class SharedDbDependencyTests(unittest.TestCase):
    def test_every_router_uses_the_one_get_db(self):
        # one dependency means one place to change how sessions are opened (and to override in tests)
        for module in (basic, games, manage, push, statistics, timers, users, utils):
            self.assertIs(module.get_db, auth.get_db, module.__name__)


if __name__ == "__main__":
    unittest.main()
