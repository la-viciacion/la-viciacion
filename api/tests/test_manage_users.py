import types
import unittest
from unittest import mock

from fastapi import HTTPException

from src.routers.manage import users


def db_with_user():
    db = mock.MagicMock()
    db.get.return_value = types.SimpleNamespace(id=2, username="bob", name="Bob", email="bob@x.es", telegram_id=None, is_admin=0, is_active=1)
    return db


class PatchUserEmailTests(unittest.TestCase):
    def patch(self, **fields):
        return users.patch_user(2, users.UserPatch(**fields), types.SimpleNamespace(id=1), db_with_user())

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
        with mock.patch.object(users.users_crud, "email_in_use", return_value=False):
            result = self.patch(email=" Bob@X.es ")
        self.assertEqual(result["email"], "bob@x.es")

    def test_leaving_the_email_out_changes_nothing_about_it(self):
        result = self.patch(name="Roberto")
        self.assertEqual(result["email"], "bob@x.es")


class GodUserProtectionTests(unittest.TestCase):
    """The emergency account is restored on every start: the panel must not be able to break or rename it."""

    def god_db(self):
        db = mock.MagicMock()
        db.get.return_value = types.SimpleNamespace(id=9, username="admin", name="Admin", email="a@x.es", telegram_id=None, is_admin=1, is_active=1)
        return db

    def patch(self, **fields):
        return users.patch_user(9, users.UserPatch(**fields), types.SimpleNamespace(id=1), self.god_db())

    def test_it_cannot_be_renamed_demoted_or_deactivated(self):
        for fields in ({"username": "otro"}, {"name": "Otro"}, {"is_admin": False}, {"is_active": False}):
            with self.assertRaises(HTTPException) as ctx:
                self.patch(**fields)
            self.assertEqual(ctx.exception.status_code, 400, fields)

    def test_sending_its_current_values_back_is_allowed(self):
        with mock.patch.object(users, "_check_username"):
            result = self.patch(username="admin", name="Admin", is_admin=True, is_active=True)
        self.assertEqual(result["username"], "admin")

    def test_its_contact_data_can_still_be_edited(self):
        with mock.patch.object(users.users_crud, "email_in_use", return_value=False):
            self.assertEqual(self.patch(email="nuevo@x.es")["email"], "nuevo@x.es")

    def test_its_password_cannot_be_set_and_it_cannot_be_deleted(self):
        with self.assertRaises(HTTPException) as ctx:
            users.set_password(9, users.PasswordBody(password="Abcdefghij1!x"), self.god_db())
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(HTTPException) as ctx:
            users.delete_user(9, True, types.SimpleNamespace(id=1), self.god_db())
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
