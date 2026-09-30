import types
import unittest
from unittest import mock

from fastapi import HTTPException

from src.routers import manage
from src.utils import email


def configure(test, **overrides):
    values = {
        "SMTP_HOST": "smtp.x", "SMTP_PORT": 587, "SMTP_EMAIL": "no-reply@x.es", "SMTP_USER": "u",
        "SMTP_PASS": "secret-pw", "SMTP_SECURITY": "starttls", "PUBLIC_URL": "https://x.es", **overrides,
    }
    for key, value in values.items():
        patcher = mock.patch.object(email.config, key, value)
        patcher.start()
        test.addCleanup(patcher.stop)


ADMIN = types.SimpleNamespace(id=1, username="admin", email="boss@x.es")


class StatusTests(unittest.TestCase):
    def test_a_complete_setup_is_configured_and_never_shows_the_password(self):
        configure(self)
        status = email.status()
        self.assertTrue(status["configured"])
        self.assertEqual(status["missing"], [])
        self.assertEqual((status["host"], status["port"], status["security"], status["from"]), ("smtp.x", 587, "starttls", "no-reply@x.es"))
        self.assertNotIn("secret-pw", str(status))

    def test_it_names_what_is_missing(self):
        configure(self, SMTP_HOST="", PUBLIC_URL="")
        status = email.status()
        self.assertFalse(status["configured"])
        self.assertEqual(status["missing"], ["SMTP_HOST", "PUBLIC_URL"])


class SettingsViewTests(unittest.TestCase):
    def test_the_settings_include_the_mail_status_and_where_a_test_goes(self):
        configure(self)
        db = mock.MagicMock()
        db.query.return_value.all.return_value = []
        db.query.return_value.scalar.return_value = 0
        with mock.patch.object(manage.settings, "public_view", return_value={}):
            result = manage.get_settings(ADMIN, db)
        self.assertEqual(result["mail"]["test_recipient"], "boss@x.es")
        self.assertTrue(result["mail"]["configured"])
        self.assertNotIn("secret-pw", str(result))


class TestEmailRouteTests(unittest.TestCase):
    def refused(self, status):
        with self.assertRaises(HTTPException) as ctx:
            manage.send_test_email(ADMIN)
        self.assertEqual(ctx.exception.status_code, status, ctx.exception.detail)
        return ctx.exception.detail

    def test_it_is_a_plain_def_because_smtp_blocks(self):
        import inspect

        self.assertFalse(inspect.iscoroutinefunction(manage.send_test_email))

    def test_without_configuration_it_says_what_is_missing(self):
        configure(self, SMTP_HOST="")
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            self.assertIn("SMTP_HOST", self.refused(409))
        smtp.assert_not_called()

    def test_an_admin_without_email_is_told_how_to_add_one(self):
        configure(self)
        admin = types.SimpleNamespace(id=1, username="admin", email=None)
        with self.assertRaises(HTTPException) as ctx:
            manage.send_test_email(admin)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Usuarios", ctx.exception.detail)

    def test_the_test_goes_to_the_email_of_whoever_asks(self):
        configure(self)
        with mock.patch.object(email.smtplib, "SMTP") as smtp:
            result = manage.send_test_email(ADMIN)
        sent = smtp.return_value.send_message.call_args.args[0]
        self.assertEqual(sent["To"], "boss@x.es")
        self.assertIn("prueba", sent["Subject"])
        self.assertIn("smtp.x:587", sent.get_content())
        self.assertNotIn("secret-pw", sent.as_string())
        self.assertIn("boss@x.es", result["message"])

    def test_a_server_failure_is_a_502_with_the_reason(self):
        configure(self)
        with mock.patch.object(email.smtplib, "SMTP", side_effect=OSError("Connection refused")):
            self.assertIn("Connection refused", self.refused(502))


if __name__ == "__main__":
    unittest.main()
