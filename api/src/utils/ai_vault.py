"""The vault of a player's own AI keys: how they are encrypted so that no copy of the server can read them.

A copy of the database alone is useless (nothing in it is a key). A copy of the whole server, the database **and** the `.env`, still
cannot read them: what opens them is the player's **password**, which only they know and the server sees at the moment they log in.

  DEK      a random 256-bit **data key**, one per player. It encrypts each of their provider keys (AES-256-GCM, bound to the player
           and the provider, so a value cannot be moved to another row).
  KEK      the key that wraps the DEK: scrypt of the password (with its own salt), mixed with a pepper taken from the `.env`
           (`SECRET_KEY`), so that the password alone is not enough either. Only the wrapped DEK is stored.
  claim    what a session carries to use the keys: the DEK encrypted with another key of the `.env`, inside the token (utils/auth).
           It is never stored: a copy of the server holds no claim, so no DEK that was open.

To open a vault you need the database, the `.env` and the password. Changing the password wraps the same DEK again with the new one;
a password that is reset (a recovery link, an admin) cannot open the old vault, so its keys are deleted (utils/user_ai.py).

It does not protect against a server that is compromised while a player uses a key: the server has to see it to send it to the
provider. Everything here is pure: it stores nothing and reads nothing but `SECRET_KEY`."""
import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import Config

config = Config()

# scrypt: n * r * 128 bytes of memory (32 MiB) and about a tenth of a second. The parameters are stored with each vault, so they can
# be raised later without breaking the vaults that exist.
KDF = {"n": 2**15, "r": 8, "p": 1}
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
MAX_MEMORY = 128 * 1024 * 1024


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


def _derive(secret: str, info: bytes) -> bytes:
    """A key of the `.env` for one purpose, so that the pepper and the key of the claims are never the same as each other or as the
    one that signs the sessions."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=info).derive(secret.encode())


def _kek(password: str, salt: bytes, kdf: dict) -> bytes:
    stretched = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=kdf["n"], r=kdf["r"], p=kdf["p"], maxmem=MAX_MEMORY, dklen=KEY_BYTES)
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=_derive(config.SECRET_KEY, b"lv-ai-vault-pepper"), info=b"lv-ai-vault-kek").derive(stretched)


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> str:
    nonce = os.urandom(NONCE_BYTES)
    return _b64(nonce + AESGCM(key).encrypt(nonce, plaintext, aad))


def _unseal(key: bytes, token: str | None, aad: bytes) -> bytes | None:
    if not token:
        return None
    try:
        raw = _unb64(token)
        return AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad)
    except (InvalidTag, ValueError, TypeError):
        return None


# ── the vault: the DEK wrapped with the password ────────────────────────────
def wrap(user_id: int, dek: bytes, password: str) -> dict:
    """The record to store for `dek` and `password`: the salt, the scrypt parameters and the wrapped DEK. Nothing in it is a secret."""
    salt = os.urandom(SALT_BYTES)
    return {"salt": _b64(salt), "kdf": dict(KDF), "wrapped": _seal(_kek(password, salt, KDF), dek, _aad(user_id, "dek"))}


def create(user_id: int, password: str) -> tuple[dict, bytes]:
    """A new vault: (the record to store, the DEK, which is only for this call and for the claim of the session)."""
    dek = os.urandom(KEY_BYTES)
    return wrap(user_id, dek, password), dek


def open_vault(user_id: int, record: dict, password: str) -> bytes | None:
    """The DEK of a stored vault, or None if the password is not the one it was wrapped with (or the record was tampered with)."""
    try:
        kdf = {name: int(record["kdf"][name]) for name in ("n", "r", "p")}
        return _unseal(_kek(password, _unb64(record["salt"]), kdf), record["wrapped"], _aad(user_id, "dek"))
    except (KeyError, ValueError, TypeError):
        return None


def _aad(user_id: int, what: str) -> bytes:
    return f"lv-ai|{user_id}|{what}".encode()


# ── the keys: sealed with the DEK ───────────────────────────────────────────
def seal_key(dek: bytes, user_id: int, provider: str, api_key: str) -> str:
    return _seal(dek, api_key.encode("utf-8"), _aad(user_id, f"key:{provider}"))


def unseal_key(dek: bytes, user_id: int, provider: str, token: str | None) -> str | None:
    found = _unseal(dek, token, _aad(user_id, f"key:{provider}"))
    return found.decode("utf-8") if found else None


# ── the claim: what a session carries to open the keys ──────────────────────
def _claims() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive(config.SECRET_KEY, b"lv-ai-unlock")))


def claim(user_id: int, dek: bytes) -> str:
    """The DEK for the token of a session: encrypted with a key of the `.env`, bound to the player and timestamped."""
    return _claims().encrypt(f"{user_id}:".encode() + dek).decode()


def open_claim(user_id: int, token: str | None, ttl_seconds: int) -> bytes | None:
    """The DEK a claim carries, or None if it is not for this player, is older than `ttl_seconds` or is not ours."""
    if not token:
        return None
    try:
        raw = _claims().decrypt(token.encode(), ttl=ttl_seconds)
    except (InvalidToken, ValueError, TypeError):
        return None
    prefix, _, dek = raw.partition(b":")
    return dek if prefix == str(user_id).encode() and len(dek) == KEY_BYTES else None
