"""Configuration loaded from the environment and the project's `.env` file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 25879


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value) if value not in (None, "") else default
    except ValueError:
        n = default
    return max(lo, min(hi, n))


@dataclass(frozen=True)
class Settings:
    port: int
    allow_external_access: bool
    data_dir: Path
    database_url: str
    secret_key: str | None
    poll_interval_minutes: int
    poll_batch_size: int
    secure_cookies: bool
    session_days: int
    log_level: str

    @property
    def host(self) -> str:
        return "0.0.0.0" if self.allow_external_access else "127.0.0.1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Real environment wins over .env, so systemd overrides keep working.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    env = os.environ

    data_dir = Path(env.get("XMENDER_DATA_DIR") or PROJECT_ROOT / "data")
    if not data_dir.is_absolute():
        data_dir = (PROJECT_ROOT / data_dir).resolve()

    database_url = env.get("XMENDER_DATABASE_URL") or f"sqlite:///{data_dir / 'xmender.db'}"

    return Settings(
        port=_int(env.get("XMENDER_PORT"), DEFAULT_PORT, 1, 65535),
        allow_external_access=_bool(env.get("XMENDER_ALLOW_EXTERNAL_ACCESS")),
        data_dir=data_dir,
        database_url=database_url,
        secret_key=env.get("XMENDER_SECRET_KEY") or None,
        poll_interval_minutes=_int(env.get("XMENDER_POLL_INTERVAL_MINUTES"), 5, 1, 60),
        poll_batch_size=_int(env.get("XMENDER_POLL_BATCH_SIZE"), 25, 1, 500),
        secure_cookies=_bool(env.get("XMENDER_SECURE_COOKIES")),
        session_days=_int(env.get("XMENDER_SESSION_DAYS"), 14, 1, 365),
        log_level=(env.get("XMENDER_LOG_LEVEL") or "INFO").upper(),
    )
