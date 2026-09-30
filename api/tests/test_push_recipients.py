import types
import unittest
from unittest import mock

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Query

from src.database import models
from src.routers import manage
from src.utils import push


class ActiveUsersOnlyTests(unittest.TestCase):
    def test_devices_are_limited_to_active_accounts(self):
        query = push.active_users_only(Query(models.PushSubscription))
        sql = str(query.statement.compile(dialect=mysql.dialect()))
        self.assertIn("push_subscriptions.user_id IN (SELECT users.id", sql)
        self.assertIn("users.is_active = %s", sql)


class DeleteUserTests(unittest.TestCase):
    def test_the_devices_of_a_deleted_user_go_with_it(self):
        db = mock.MagicMock()
        db.get.return_value = types.SimpleNamespace(id=5)
        admin = types.SimpleNamespace(id=1)
        manage.delete_user(5, force=True, admin=admin, db=db)
        queried = [c.args[0] for c in db.query.call_args_list]
        self.assertIn(models.PushSubscription, queried)


if __name__ == "__main__":
    unittest.main()
