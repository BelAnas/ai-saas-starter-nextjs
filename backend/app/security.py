"""Password hashing and session tokens, using only the standard library."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

# scrypt is memory-hard, which makes guessing passwords on GPUs expensive.
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    # The parameters are stored with the hash so they can be raised later without a migration.
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(key_b64)
        key = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p),
                             dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(key, expected)


# Checked when the email is unknown, so a wrong email takes as long as a wrong password.
DUMMY_HASH = hash_password("not-a-real-password")


def new_session_token() -> tuple[str, str]:
    """Return (token for the cookie, hash for the database)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    # A fast hash is enough here: the token is 256 random bits, not a human password.
    return hashlib.sha256(token.encode()).hexdigest()
