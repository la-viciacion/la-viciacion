"""How a player's own AI keys follow their session and their password: the token that carries the data key (login, renewal), how a
route reads it, and what happens to the vault when their own password changes (the keys follow) or is reset by a link or an admin (the
keys go: nobody can open them any more)."""
import types
import unittest
from unittest import mock

import jwt
from bcrypt import gensalt, hashpw
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src import auth
from src.database import models, schemas
from src.routers import basic
from src.routers import users as users_router
from src.routers.manage import users as manage_users
from src.utils import ai_vault, password_reset, user_ai
from tests import ai_env
from tests.sqlite_db import make_session
from tests.test_chat import seed

PASSWORD = "Una-Contrasena-Muy-Larga-1!"
NEW_PASSWORD = "La-Nueva-Contrasena-2@"
KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
GOOGLE_KEY = "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456"


def claim_of(token: str):
    return jwt.decode(token, auth.config.SECRET_KEY, algorithms=[auth.ALGORITHM]).get("ku")


class Base(unittest.TestCase):
    def setUp(self):
        self.db = make_session(threads=True)
        seed(self.db)
        ai_env.free_wallet(self.db)
        for user in self.db.query(models.User).filter(models.User.id.in_((1, 2))).all():
            user.password = hashpw(PASSWORD.encode(), gensalt(4)).decode()
            user.email = f"{user.username}@example.com"
        self.db.commit()
        self.ana = self.db.get(models.User, 1)
        patcher = mock.patch.object(ai_vault, "KDF", ai_env.FAST_KDF)
        patcher.start()
        self.addCleanup(patcher.stop)


class TokenTests(Base):
    def test_a_token_carries_the_data_key_only_when_it_is_given_one(self):
        dek = b"\x05" * 32
        with_key = auth.issue_token(self.ana, dek)["access_token"]
        without = auth.issue_token(self.ana)["access_token"]
        self.assertEqual(ai_vault.open_claim(1, claim_of(with_key), 3600), dek)
        self.assertIsNone(claim_of(without))
        self.assertNotIn(ai_vault._b64(dek), with_key, "the data key is not in the token as it is")

    def test_the_dependency_gives_the_data_key_of_the_session_and_nothing_to_a_session_without_it(self):
        dek = b"\x05" * 32
        self.assertEqual(auth.get_unlock(auth.issue_token(self.ana, dek)["access_token"], self.ana), dek)
        self.assertIsNone(auth.get_unlock(auth.issue_token(self.ana)["access_token"], self.ana), "an old session: locked")
        self.assertIsNone(auth.get_unlock("not a token", self.ana))

    def test_a_claim_of_another_player_or_an_expired_one_opens_nothing(self):
        dek = b"\x05" * 32
        token = auth.issue_token(self.ana, dek)["access_token"]
        beto = self.db.get(models.User, 2)
        self.assertIsNone(auth.get_unlock(token, beto), "the claim is bound to its player")
        with mock.patch("cryptography.fernet.time.time", return_value=__import__("time").time() + 7 * 24 * 3600 + 60):
            self.assertIsNone(auth.get_unlock(token, self.ana), "it lasts as long as a session")


class LoginTests(Base):
    def setUp(self):
        super().setUp()
        basic.LOGIN_BY_ACCOUNT.reset("ana")
        app = FastAPI()
        app.include_router(basic.router)
        app.dependency_overrides[basic.get_db] = lambda: self.db
        self.client = TestClient(app)
        self.addCleanup(basic.LOGIN_BY_ACCOUNT.reset, "ana")
        patcher = mock.patch.object(basic.audit, "record_event")
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, user="ana", password=PASSWORD):
        return self.client.post("/token", data={"username": user, "password": password})

    def test_a_player_with_nothing_to_keep_gets_an_ordinary_token_and_no_vault_is_made(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(claim_of(response.json()["access_token"]))
        self.assertEqual(self.db.query(models.UserAiVault).count(), 0)

    def test_a_player_with_a_vault_gets_its_data_key_in_the_token(self):
        dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        token = self.login().json()["access_token"]
        self.assertEqual(ai_vault.open_claim(1, claim_of(token), 3600), dek)
        self.assertEqual(auth.get_unlock(token, self.ana), dek)

    def test_a_wrong_password_gets_nothing_and_opens_nothing(self):
        ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        self.assertEqual(self.login(password="nope").status_code, 401)

    def test_a_vault_that_cannot_be_read_never_stops_the_login_the_session_is_just_locked(self):
        ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        with mock.patch.object(basic.user_ai, "unlock", side_effect=RuntimeError("boom")), self.assertLogs(basic.logger, "ERROR"):
            response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(claim_of(response.json()["access_token"]))

    def test_the_renewal_keeps_the_data_key_with_a_fresh_claim_and_adds_none_to_a_locked_session(self):
        dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        app = self.client.app
        app.dependency_overrides[auth.get_current_active_user] = lambda: self.ana
        app.dependency_overrides[auth.get_unlock] = lambda: dek
        renewed = self.client.post("/auth/refresh").json()["access_token"]
        self.assertEqual(ai_vault.open_claim(1, claim_of(renewed), 3600), dek)
        old = auth.issue_token(self.ana, dek)["access_token"]
        self.assertNotEqual(claim_of(renewed), claim_of(old), "a new claim: the key lasts as long as the session, not as the first one")
        app.dependency_overrides[auth.get_unlock] = lambda: None
        self.assertIsNone(claim_of(self.client.post("/auth/refresh").json()["access_token"]))


class PasswordFlowsTests(Base):
    def keys_of(self, user_id, password):
        dek = user_ai.unlock(self.db, user_id, password, create=False)
        return user_ai.credentials(self.db, user_id, dek, "openai") if dek else None

    def setUp(self):
        super().setUp()
        self.dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        user_ai.save(self.db, 1, self.dek, "google", GOOGLE_KEY)

    def test_changing_their_own_password_takes_the_keys_to_the_new_one(self):
        request = mock.Mock()
        body = schemas.PasswordChange(current_password=PASSWORD, new_password=NEW_PASSWORD)
        with mock.patch.object(users_router.audit, "record_event"):
            users_router.change_password(request, "ana", body, self.ana, self.db)
        self.assertIsNone(user_ai.unlock(self.db, 1, PASSWORD, create=False), "the old password opens nothing")
        self.assertEqual(self.keys_of(1, NEW_PASSWORD), (KEY, "gpt-4.1-mini"))
        self.assertEqual(user_ai.providers_with_key(self.db, 1), ["openai", "google"])

    def test_a_wrong_current_password_changes_nothing_not_even_the_vault(self):
        body = schemas.PasswordChange(current_password="nope", new_password=NEW_PASSWORD)
        with mock.patch.object(users_router.audit, "record_event"), self.assertRaises(HTTPException) as caught:
            users_router.change_password(mock.Mock(), "ana", body, self.ana, self.db)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(self.keys_of(1, PASSWORD), (KEY, "gpt-4.1-mini"))

    def test_a_password_reset_by_a_recovery_link_deletes_their_keys(self):
        token = password_reset.create_token(self.db, self.ana)
        with self.assertLogs(password_reset.logger, "INFO"):
            self.assertTrue(password_reset.reset_password(self.db, token, NEW_PASSWORD))
        self.assertEqual((user_ai.providers_with_key(self.db, 1), self.db.query(models.UserAiVault).count()), ([], 0))
        self.assertIsNone(user_ai.unlock(self.db, 1, NEW_PASSWORD, create=False))

    def test_a_link_that_does_not_work_touches_nothing(self):
        self.assertFalse(password_reset.reset_password(self.db, "not a token", NEW_PASSWORD))
        self.assertEqual(self.keys_of(1, PASSWORD), (KEY, "gpt-4.1-mini"))

    def test_a_password_set_by_an_admin_deletes_their_keys_and_says_so(self):
        answer = manage_users.set_password(1, manage_users.PasswordBody(password=NEW_PASSWORD), self.db)
        self.assertIn("claves de IA borradas", answer["message"])
        self.assertEqual(user_ai.providers_with_key(self.db, 1), [])

    def test_an_admin_setting_the_password_of_a_player_with_no_keys_says_nothing_about_them(self):
        answer = manage_users.set_password(2, manage_users.PasswordBody(password=NEW_PASSWORD), self.db)
        self.assertEqual(answer, {"message": "Contraseña actualizada"})

    def test_only_the_player_whose_password_changed_loses_their_keys(self):
        user_ai.save(self.db, 2, user_ai.unlock(self.db, 2, PASSWORD), "openai", KEY)
        manage_users.set_password(1, manage_users.PasswordBody(password=NEW_PASSWORD), self.db)
        self.assertEqual(self.keys_of(2, PASSWORD), (KEY, "gpt-4.1-mini"))


class ChatAndGuideRoutesTests(Base):
    """The routes that use a key answer 423 when the player has keys that this session cannot open."""

    def setUp(self):
        super().setUp()
        from src.routers import chat as chat_router
        from src.routers import guide as guide_router
        from tests.test_ai_budget import patched

        self.dek = ai_env.give_key(self.db, 1, KEY, "gpt-4.1-mini", password=PASSWORD)
        self.locked = False
        app = FastAPI()
        app.include_router(chat_router.router)
        app.include_router(guide_router.router)
        app.dependency_overrides[auth.get_current_active_user] = lambda: types.SimpleNamespace(id=1, username="ana", name="Ana", is_admin=0, is_active=1)
        app.dependency_overrides[auth.get_unlock] = lambda: None if self.locked else self.dek
        app.dependency_overrides[chat_router.get_db] = lambda: self.db
        self.client = TestClient(app)
        chat_router.limits.limiter.clear()
        for patcher in (patched(**{"chat.key_source": "user_only", "guide.key_source": "user_only", "ai.openai.api_key": None}),):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_locked_session_is_told_to_unlock_and_still_sees_the_chat_button(self):
        self.locked = True
        self.assertTrue(self.client.get("/chat/status").json()["available"])
        for response in (self.client.post("/chat", json={"message": "hola"}), self.client.post("/guide/g1", json={"message": "hola"})):
            self.assertEqual(response.status_code, 423)
            self.assertIn("contraseña", response.json()["detail"])
        self.assertEqual(self.db.query(models.AiUsage).count(), 0, "nothing was asked and nothing was recorded")

    def test_an_unlocked_session_uses_the_key_of_the_player(self):
        from src.routers import chat as chat_router

        with mock.patch.object(chat_router.agent, "ask", return_value=chat_router.agent.Answer("Hola", True)) as ask:
            response = self.client.post("/chat", json={"message": "hola"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((ask.call_args.kwargs["source"].api_key, ask.call_args.kwargs["source"].provider), (KEY, "openai"))

    def test_the_guide_status_says_locked_and_not_that_a_key_is_needed(self):
        self.locked = True
        body = self.client.get("/guide/status").json()
        self.assertEqual((body["locked"], body["needs_key"], body["available"]), (True, False, True))
        self.locked = False
        body = self.client.get("/guide/status").json()
        self.assertEqual((body["locked"], body["needs_key"], body["paid_by"]), (False, False, "user"))




if __name__ == "__main__":
    unittest.main()
