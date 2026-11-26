"""Shared API dependencies: auth, permissions, app settings."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppSetting, AuthSession, User, as_utc, utcnow
from ..security import hash_token

COOKIE_NAME = "xmender_session"

APP_SETTING_DEFAULTS: dict[str, Any] = {"registration_enabled": False}


def get_app_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    return row.value if row else APP_SETTING_DEFAULTS.get(key)


def set_app_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    sess = db.get(AuthSession, hash_token(raw))
    if sess is None:
        return None
    if as_utc(sess.expires_at) < utcnow():
        db.delete(sess)
        return None
    return sess.user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Not logged in.")
    if user.must_change_password:
        raise HTTPException(403, "Password change required.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.has_admin():
        raise HTTPException(403, "Admin only.")
    return user


def require(permission: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not user.can(permission):
            raise HTTPException(403, f"Missing permission: {permission}.")
        return user

    return dep


class LoginThrottle:
    """Per-client failure counter; blocks after too many recent failures."""

    def __init__(self, limit: int = 10, window: float = 600) -> None:
        self.limit, self.window = limit, window
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str) -> deque[float]:
        q, now = self._fails[key], time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def check(self, key: str) -> None:
        if len(self._trim(key)) >= self.limit:
            raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")

    def fail(self, key: str) -> None:
        self._trim(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


throttle = LoginThrottle()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def user_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "is_root": u.is_root,
        "is_admin": u.has_admin(),
        "permissions": list(u.permissions or []),
        "default_model": u.default_model,
        "timezone": u.timezone,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
