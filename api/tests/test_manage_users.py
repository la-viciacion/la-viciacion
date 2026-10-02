import types
import unittest
from unittest import mock

from fastapi import HTTPException

from src.routers import manage


def db_with_user():
    db = mock.MagicMock()
    db.get.return_value = types.SimpleNamespace(id=2, username="bob", name="Bob", email="bob@x.es", telegram_id=None, is_admin=0, is_active=1)
    return db


class PatchUserEmailTests(unittest.TestCase):
    def patch(self, **fields):
        return manage.patch_user(2, manage.UserPatch(**fields), types.SimpleNamespace(id=1), db_with_user())

    def test_the_email_cannot_be_removed(self):
        for email in (None, "", "  "):
            with self.assertRaises(HTTPException) as ctx:
                self.patch(email=email)
            self.assertEqual(ctx.exception.status_code, 400, repr(email))

    def test_a_malformed_email_is_refused(self):
        with self.assertRaises(HTTPException) as ctx:
            self.patch(email="not-an-email")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_a_valid_email_is_normalized_and_saved(self):
        with mock.patch.object(manage.users_crud, "email_in_use", return_value=False):
            result = self.patch(email=" Bob@X.es ")
        self.assertEqual(result["email"], "bob@x.es")

    def test_leaving_the_email_out_changes_nothing_about_it(self):
        result = self.patch(name="Roberto")
        self.assertEqual(result["email"], "bob@x.es")


if __name__ == "__main__":
    unittest.main()
