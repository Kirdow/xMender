"""Password hashing, secret encryption and session tokens."""

from __future__ import annotations

import hashlib
import os
import secrets
import string
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Precomputed so failed logins for unknown users take as long as real ones.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def burn_verify_time(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 256:
        return "Password is too long."
    return None


def generate_temp_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def new_session_token() -> tuple[str, str]:
    """Returns (raw token for the cookie, hash to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.secret_key
    if not key:
        path = settings.data_dir / "secret.key"
        if path.exists():
            key = path.read_text().strip()
        else:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key().decode()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(key + "\n")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError(
            "Stored secret cannot be decrypted; was XMENDER_SECRET_KEY or secret.key changed?"
        ) from e
