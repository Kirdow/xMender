"""Login, logout, first-time admin setup, registration, own account."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import DEFAULT_PERMISSIONS, AuthSession, User, utcnow
from ..security import (
    burn_verify_time,
    hash_password,
    hash_token,
    new_session_token,
    password_problem,
    verify_password,
)
from .deps import (
    COOKIE_NAME,
    client_key,
    current_user,
    get_app_setting,
    optional_user,
    throttle,
    user_dict,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def username_problem(name: str) -> str | None:
    if not USERNAME_RE.match(name):
        return "Username must be 3-32 characters: letters, digits, `_`, `.`, `-`."
    return None


class LoginBody(BaseModel):
    username: str
    password: str


class SetupBody(BaseModel):
    temp_password: str
    new_password: str


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


def _start_session(db: Session, response: Response, user: User) -> None:
    settings = get_settings()
    raw, hashed = new_session_token()
    expires = utcnow() + timedelta(days=settings.session_days)
    db.add(AuthSession(token_hash=hashed, user_id=user.id, expires_at=expires))
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="strict",
        secure=settings.secure_cookies,
        path="/",
    )


def _root(db: Session) -> User | None:
    return db.scalar(select(User).where(User.is_root.is_(True)))


@router.get("/state")
def state(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    root = _root(db)
    return {
        "setup_required": bool(root and root.must_change_password),
        "registration_enabled": bool(get_app_setting(db, "registration_enabled")),
        "user": user_dict(user) if user and not user.must_change_password else None,
    }


@router.post("/setup")
def setup(body: SetupBody, request: Request, response: Response, db: Session = Depends(get_db)):
    key = "setup:" + client_key(request)
    throttle.check(key)
    root = _root(db)
    if root is None or not root.must_change_password:
        raise HTTPException(409, "Setup is already complete.")
    if not verify_password(root.password_hash, body.temp_password.strip()):
        throttle.fail(key)
        raise HTTPException(400, "Temporary password is wrong. Copy it from the service output.")
    if problem := password_problem(body.new_password):
        raise HTTPException(400, problem)
    if body.new_password == body.temp_password.strip():
        raise HTTPException(400, "Choose a new password, not the temporary one.")
    throttle.reset(key)
    root.password_hash = hash_password(body.new_password)
    root.must_change_password = False
    db.execute(delete(AuthSession).where(AuthSession.user_id == root.id))
    _start_session(db, response, root)
    return {"user": user_dict(root)}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    key = "login:" + client_key(request)
    throttle.check(key)
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    if user is None:
        burn_verify_time(body.password)
        throttle.fail(key)
        raise HTTPException(401, "Wrong username or password.")
    if user.must_change_password:
        raise HTTPException(403, "This account still needs first-time setup.")
    if not verify_password(user.password_hash, body.password):
        throttle.fail(key)
        raise HTTPException(401, "Wrong username or password.")
    throttle.reset(key)
    _start_session(db, response, user)
    return {"user": user_dict(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(raw)))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/register")
def register(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_app_setting(db, "registration_enabled"):
        raise HTTPException(403, "Account creation is disabled.")
    key = "register:" + client_key(request)
    throttle.check(key)
    name = body.username.strip()
    if problem := username_problem(name) or password_problem(body.password):
        raise HTTPException(400, problem)
    if db.scalar(select(User).where(func.lower(User.username) == name.lower())):
        throttle.fail(key)
        raise HTTPException(409, "Username is taken.")
    user = User(
        username=name,
        password_hash=hash_password(body.password),
        permissions=list(DEFAULT_PERMISSIONS),
    )
    db.add(user)
    db.flush()
    _start_session(db, response, user)
    return {"user": user_dict(user)}


@router.post("/password")
def change_password(body: PasswordBody, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Current password is wrong.")
    if problem := password_problem(body.new_password):
        raise HTTPException(400, problem)
    user.password_hash = hash_password(body.new_password)
    # Sign out other sessions.
    keep = hash_token(request.cookies.get(COOKIE_NAME, ""))
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != keep)
    )
    return {"ok": True}
