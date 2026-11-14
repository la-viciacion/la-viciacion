"""How a player's AI keys are encrypted: what opens the vault (their password, with the .env), what a stolen copy contains, how the
keys are bound to the player and the provider, and the claim a session carries."""
import copy
import json
import time
import unittest
from unittest import mock

from src.utils import ai_vault

PASSWORD = "Una-Contrasena-Muy-Larga-1!"
API_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
FAST = {"n": 2**8, "r": 8, "p": 1}  # the tests do not need the real cost of an attacker


def fast(test):
    """Runs a test with a cheap scrypt, except the ones that look at the real parameters."""
    def wrapped(self):
        with mock.patch.object(ai_vault, "KDF", FAST):
            test(self)

    wrapped.__name__ = test.__name__
    return wrapped


class VaultTests(unittest.TestCase):
    @fast
    def test_the_password_opens_the_vault_and_gives_the_data_key_back(self):
        record, dek = ai_vault.create(7, PASSWORD)
        self.assertEqual(len(dek), 32)
        self.assertEqual(ai_vault.open_vault(7, record, PASSWORD), dek)

    @fast
    def test_a_wrong_password_a_wrong_player_and_a_tampered_record_open_nothing(self):
        record, _ = ai_vault.create(7, PASSWORD)
        self.assertIsNone(ai_vault.open_vault(7, record, PASSWORD + "x"))
        self.assertIsNone(ai_vault.open_vault(8, record, PASSWORD), "bound to its player")
        broken = copy.deepcopy(record)
        broken["wrapped"] = broken["wrapped"][:-4] + "AAAA"
        self.assertIsNone(ai_vault.open_vault(7, broken, PASSWORD))
        for bad in ({}, {"salt": "x"}, {"salt": record["salt"], "kdf": {"n": "x", "r": 8, "p": 1}, "wrapped": record["wrapped"]}):
            self.assertIsNone(ai_vault.open_vault(7, bad, PASSWORD), bad)

    @fast
    def test_the_stored_record_holds_no_secret_and_is_never_the_same_twice(self):
        record, dek = ai_vault.create(7, PASSWORD)
        text = json.dumps(record)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn(ai_vault._b64(dek), text)
        other, _ = ai_vault.create(7, PASSWORD)
        self.assertNotEqual(record["salt"], other["salt"])
        self.assertNotEqual(record["wrapped"], other["wrapped"])

    @fast
    def test_a_copy_of_the_database_with_the_password_but_without_the_env_opens_nothing(self):
        """The pepper of the .env is part of the key: the password alone is not enough."""
        record, _ = ai_vault.create(7, PASSWORD)
        with mock.patch.object(ai_vault.config, "SECRET_KEY", "another-secret-key-of-another-server-000000"):
            self.assertIsNone(ai_vault.open_vault(7, record, PASSWORD))

    @fast
    def test_changing_the_password_wraps_the_same_data_key_again(self):
        record, dek = ai_vault.create(7, PASSWORD)
        again = ai_vault.wrap(7, ai_vault.open_vault(7, record, PASSWORD), "La-Nueva-Contrasena-2@")
        self.assertEqual(ai_vault.open_vault(7, again, "La-Nueva-Contrasena-2@"), dek)
        self.assertIsNone(ai_vault.open_vault(7, again, PASSWORD), "the old password no longer opens it")
        self.assertNotEqual(again["salt"], record["salt"])

    @fast
    def test_the_parameters_stored_with_the_vault_are_the_ones_used_to_open_it(self):
        record, dek = ai_vault.create(7, PASSWORD)
        with mock.patch.object(ai_vault, "KDF", {"n": 2**9, "r": 8, "p": 1}):  # the code's parameters move on: the old vault still opens
            self.assertEqual(ai_vault.open_vault(7, record, PASSWORD), dek)
        tampered = {**record, "kdf": {"n": 2**9, "r": 8, "p": 1}}
        self.assertIsNone(ai_vault.open_vault(7, tampered, PASSWORD))

    def test_the_real_parameters_are_costly_enough_and_fit_the_memory_limit(self):
        self.assertGreaterEqual(ai_vault.KDF["n"], 2**15)
        self.assertLessEqual(128 * ai_vault.KDF["n"] * ai_vault.KDF["r"], ai_vault.MAX_MEMORY)
        started = time.perf_counter()
        record, dek = ai_vault.create(7, PASSWORD)
        self.assertEqual(ai_vault.open_vault(7, record, PASSWORD), dek)
        self.assertLess(time.perf_counter() - started, 5, "two derivations are about a fifth of a second, not seconds")


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.dek = b"\x01" * 32

    def test_a_key_is_sealed_with_the_data_key_and_opens_only_with_it(self):
        sealed = ai_vault.seal_key(self.dek, 7, "openai", API_KEY)
        self.assertNotIn(API_KEY, sealed)
        self.assertNotIn(API_KEY[-4:], sealed)
        self.assertEqual(ai_vault.unseal_key(self.dek, 7, "openai", sealed), API_KEY)
        self.assertIsNone(ai_vault.unseal_key(b"\x02" * 32, 7, "openai", sealed))

    def test_a_sealed_key_cannot_be_moved_to_another_player_or_provider(self):
        sealed = ai_vault.seal_key(self.dek, 7, "openai", API_KEY)
        self.assertIsNone(ai_vault.unseal_key(self.dek, 8, "openai", sealed))
        self.assertIsNone(ai_vault.unseal_key(self.dek, 7, "anthropic", sealed))

    def test_nothing_or_garbage_opens_to_nothing(self):
        for bad in (None, "", "not base64 at all!", ai_vault._b64(b"short")):
            self.assertIsNone(ai_vault.unseal_key(self.dek, 7, "openai", bad), bad)

    def test_the_same_key_sealed_twice_differs(self):
        self.assertNotEqual(ai_vault.seal_key(self.dek, 7, "openai", API_KEY), ai_vault.seal_key(self.dek, 7, "openai", API_KEY))


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.dek = b"\x03" * 32

    def test_the_claim_carries_the_data_key_for_its_player_only(self):
        token = ai_vault.claim(7, self.dek)
        self.assertEqual(ai_vault.open_claim(7, token, 3600), self.dek)
        self.assertIsNone(ai_vault.open_claim(8, token, 3600))
        self.assertNotIn(ai_vault._b64(self.dek), token)

    def test_it_expires_with_the_session(self):
        token = ai_vault.claim(7, self.dek)
        with mock.patch("cryptography.fernet.time.time", return_value=time.time() + 3601):
            self.assertIsNone(ai_vault.open_claim(7, token, 3600))
        with mock.patch("cryptography.fernet.time.time", return_value=time.time() + 3000):
            self.assertEqual(ai_vault.open_claim(7, token, 3600), self.dek)

    def test_a_claim_of_another_server_or_garbage_opens_nothing(self):
        token = ai_vault.claim(7, self.dek)
        with mock.patch.object(ai_vault.config, "SECRET_KEY", "another-secret-key-of-another-server-000000"):
            self.assertIsNone(ai_vault.open_claim(7, token, 3600))
        for bad in (None, "", "garbage", token[:-3] + "AAA"):
            self.assertIsNone(ai_vault.open_claim(7, bad, 3600), bad)

    def test_the_key_of_the_claims_is_not_the_one_of_the_sessions_nor_the_pepper(self):
        secret = ai_vault.config.SECRET_KEY
        keys = {ai_vault._derive(secret, b"lv-ai-unlock"), ai_vault._derive(secret, b"lv-ai-vault-pepper"), secret.encode()[:32].ljust(32, b"0")}
        self.assertEqual(len(keys), 3)


if __name__ == "__main__":
    unittest.main()
