"""Login, sessions and password recovery, through real requests (MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta
from unittest import mock

import jwt
from sqlalchemy import text

from src import auth
from src.database import database, models
from src.routers import basic
from src.utils import messages, password_reset
from tests.api_support import PASSWORD, ApiTestCase

NEW_PASSWORD = "An0ther-secret!pw"


class LoginTests(ApiTestCase):
    def login(self, username, password=PASSWORD):
        return self.api("POST", "/token", data={"username": username, "password": password})

    def test_the_service_answers_without_a_token(self):
        self.assertEqual(self.api("GET", "/").status_code, 200)
        self.assertEqual(self.api("GET", "/keepalive").status_code, 200)

    def test_a_correct_login_returns_a_token_that_opens_the_session(self):
        self.user("ana", email="Ana@Example.com")
        response = self.login("ana")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token_type"], "bearer")
        claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
        self.assertEqual((claims["username"], claims["is_admin"], claims["is_active"]), ("ana", 0, 1))
        me = self.api("GET", "/auth/active_user", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
        self.assertEqual((me.status_code, me.json()["username"]), (200, "ana"))

    def test_the_login_accepts_the_email_in_any_case(self):
        self.user("ana", email="ana@example.com")
        self.assertEqual(self.login("ANA@Example.COM").status_code, 200)

    def test_a_wrong_password_and_an_unknown_user_get_the_same_answer(self):
        self.user("ana")
        wrong, unknown = self.login("ana", "not-the-password"), self.login("nobody")
        self.assertEqual((wrong.status_code, unknown.status_code), (401, 401))
        self.assertEqual(wrong.json(), unknown.json())

    def test_a_disabled_account_is_told_so_only_after_the_right_password(self):
        self.user("ana", active=False)
        self.assertEqual(self.login("ana", "wrong").status_code, 401)
        disabled = self.login("ana")
        self.assertEqual((disabled.status_code, disabled.json()["detail"]), (403, messages.ACCOUNT_DISABLED))

    def test_five_failures_block_the_account_even_for_the_right_password(self):
        self.user("ana")
        for _ in range(5):
            self.assertEqual(self.login("ana", "wrong").status_code, 401)
        blocked = self.login("ana")
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked.headers["Retry-After"]), 0)

    def test_a_success_clears_the_failures(self):
        self.user("ana")
        for _ in range(4):
            self.login("ana", "wrong")
        self.assertEqual(self.login("ana").status_code, 200)
        for _ in range(4):
            self.assertEqual(self.login("ana", "wrong").status_code, 401)

    def test_the_block_of_one_account_does_not_touch_another(self):
        self.user("ana"), self.user("bea")
        for _ in range(5):
            self.login("ana", "wrong")
        self.assertEqual(self.login("bea").status_code, 200)

    def test_only_real_client_addresses_are_counted(self):
        self.assertIsNone(basic.client_key("172.18.0.5"))  # the nginx container
        self.assertIsNone(basic.client_key("127.0.0.1"))
        self.assertIsNone(basic.client_key("testclient"))
        self.assertIsNone(basic.client_key(None))
        self.assertEqual(basic.client_key("8.8.8.8"), "8.8.8.8")


class SessionTests(ApiTestCase):
    def token(self, payload, key="ci-secret", algorithm="HS256"):
        return {"Authorization": "Bearer " + jwt.encode(payload, key, algorithm=algorithm)}

    def valid_payload(self, username="ana", **extra):
        with database.SessionLocal() as db:
            user = db.query(models.User).filter_by(username=username).one()
            return {"username": username, "pwv": auth.password_fingerprint(user),
                    "exp": datetime.datetime.now(datetime.timezone.utc) + timedelta(minutes=5), **extra}

    def test_every_protected_route_refuses_a_missing_token(self):
        self.assertEqual(self.api("GET", "/auth/active_user").status_code, 401)

    def test_a_token_signed_with_another_key_is_refused(self):
        self.user("ana")
        forged = self.token(self.valid_payload(), key="another-secret-of-enough-length-123456")
        self.assertEqual(self.api("GET", "/auth/active_user", headers=forged).status_code, 401)

    def test_an_expired_token_is_refused(self):
        self.user("ana")
        payload = self.valid_payload()
        payload["exp"] = datetime.datetime.now(datetime.timezone.utc) - timedelta(seconds=1)
        self.assertEqual(self.api("GET", "/auth/active_user", headers=self.token(payload)).status_code, 401)

    def test_a_token_without_a_username_is_refused(self):
        self.user("ana")
        payload = self.valid_payload()
        del payload["username"]
        self.assertEqual(self.api("GET", "/auth/active_user", headers=self.token(payload)).status_code, 401)

    def test_a_token_of_a_user_that_no_longer_exists_is_refused(self):
        self.user("ana")
        headers = self.headers("ana")
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE username = 'ana'"))
        self.assertEqual(self.api("GET", "/auth/active_user", headers=headers).status_code, 401)

    def test_a_token_from_before_a_password_change_is_refused(self):
        self.user("ana")
        old = self.headers("ana")
        self.assertEqual(self.api("POST", "/users/ana/password", headers=old,
                                  json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.api("GET", "/auth/active_user", headers=old).status_code, 401)

    def test_a_disabled_account_cannot_use_a_token_it_already_had(self):
        self.user("ana")
        headers = self.headers("ana")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_active = 0 WHERE username = 'ana'"))
        response = self.api("GET", "/auth/active_user", headers=headers)
        self.assertEqual((response.status_code, response.json()["detail"]), (400, "Inactive user"))


class PasswordRecoveryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        enabled = mock.patch.object(type(basic.config), "MAIL_ENABLED", new_callable=mock.PropertyMock, return_value=True)
        enabled.start()
        self.addCleanup(enabled.stop)
        sent = mock.patch.object(password_reset, "send_recovery_email")
        self.send = sent.start()
        self.addCleanup(sent.stop)

    def ask(self, login):
        return self.api("POST", "/auth/forgot-password", json={"login": login})

    def token_sent(self):
        """The link token the mocked mailer was handed (the last argument)."""
        return self.send.call_args.args[2]

    def test_without_mail_configured_it_says_so(self):
        with mock.patch.object(type(basic.config), "MAIL_ENABLED", new_callable=mock.PropertyMock, return_value=False):
            response = self.ask("ana")
        self.assertEqual((response.status_code, response.json()["detail"]), (503, messages.RECOVERY_NOT_CONFIGURED))

    def test_the_answer_is_the_same_for_an_account_that_exists_and_one_that_does_not(self):
        self.user("ana")
        known, unknown = self.ask("ana"), self.ask("nobody")
        self.assertEqual((known.status_code, unknown.status_code), (202, 202))
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(self.send.call_count, 1)  # only the real one produced an email

    def test_the_email_goes_to_the_stored_address_even_when_asked_by_username(self):
        self.user("ana", email="ana@example.com")
        self.ask("ana")
        self.assertEqual(self.send.call_args.args[0], "ana@example.com")

    def test_accounts_that_cannot_receive_the_link_get_none(self):
        self.user("off", active=False)
        self.ask("off")
        self.assertEqual(self.send.call_count, 0)

    def test_the_link_changes_the_password_once_and_signs_everybody_out(self):
        self.user("ana")
        session = self.headers("ana")
        self.ask("ana")
        token = self.token_sent()
        done = self.api("POST", "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        self.assertEqual((done.status_code, done.json()["message"]), (200, messages.PASSWORD_RESET_DONE))
        self.assertEqual(self.api("POST", "/token", data={"username": "ana", "password": NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.api("POST", "/token", data={"username": "ana", "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.api("GET", "/auth/active_user", headers=session).status_code, 401)
        again = self.api("POST", "/auth/reset-password", json={"token": token, "new_password": "Third-secret!pw1"})
        self.assertEqual((again.status_code, again.json()["detail"]), (400, messages.RECOVERY_LINK_INVALID))

    def test_a_weak_password_does_not_use_up_the_link(self):
        self.user("ana")
        self.ask("ana")
        token = self.token_sent()
        weak = self.api("POST", "/auth/reset-password", json={"token": token, "new_password": "weak"})
        self.assertEqual((weak.status_code, weak.json()["detail"]), (400, messages.PASSWORD_RULES))
        self.assertEqual(self.api("POST", "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD}).status_code, 200)

    def test_an_unknown_link_is_refused(self):
        response = self.api("POST", "/auth/reset-password", json={"token": "nope", "new_password": NEW_PASSWORD})
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.RECOVERY_LINK_INVALID))

    def test_an_expired_link_is_refused(self):
        self.user("ana")
        self.ask("ana")
        token = self.token_sent()
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE password_resets SET expires_at = :past"), {"past": datetime.datetime(2000, 1, 1)})
        response = self.api("POST", "/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        self.assertEqual(response.status_code, 400)

    def test_asking_again_invalidates_the_previous_link(self):
        self.user("ana")
        self.ask("ana")
        first = self.token_sent()
        self.ask("ana")
        second = self.token_sent()
        self.assertNotEqual(first, second)
        self.assertEqual(self.api("POST", "/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD}).status_code, 400)
        self.assertEqual(self.api("POST", "/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}).status_code, 200)

    def test_an_account_gets_three_links_an_hour_and_the_answer_does_not_change(self):
        self.user("ana")
        statuses = [self.ask("ana").status_code for _ in range(4)]
        self.assertEqual(statuses, [202, 202, 202, 202])
        self.assertEqual(self.send.call_count, 3)

    def test_the_token_is_stored_hashed(self):
        self.user("ana")
        self.ask("ana")
        stored = self.scalar("SELECT token_hash FROM password_resets")
        self.assertNotEqual(stored, self.token_sent())
        self.assertEqual(stored, password_reset.hash_token(self.token_sent()))
