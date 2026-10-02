import types
import unittest

from src import auth


class PasswordFingerprintTests(unittest.TestCase):
    def test_changes_with_the_password_hash(self):
        old = types.SimpleNamespace(password="$2b$12$oldhash")
        new = types.SimpleNamespace(password="$2b$12$newhash")
        self.assertNotEqual(auth.password_fingerprint(old), auth.password_fingerprint(new))

    def test_is_stable_and_does_not_expose_the_hash(self):
        user = types.SimpleNamespace(password="$2b$12$oldhash")
        fingerprint = auth.password_fingerprint(user)
        self.assertEqual(fingerprint, auth.password_fingerprint(user))
        self.assertNotIn("oldhash", fingerprint)
        self.assertEqual(len(fingerprint), 16)


if __name__ == "__main__":
    unittest.main()
