"""User management and app-wide settings (admins only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PERMISSIONS, AuthSession, User
from ..security import hash_password, password_problem
from .auth import username_problem
from .deps import admin_user, get_app_setting, set_app_setting, user_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUser(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    permissions: list[str] = list(PERMISSIONS)


class UpdateUser(BaseModel):
    is_admin: bool | None = None
    permissions: list[str] | None = None
    password: str | None = None


class AppSettingsBody(BaseModel):
    registration_enabled: bool


def _perms(values: list[str]) -> list[str]:
    bad = [p for p in values if p not in PERMISSIONS]
    if bad:
        raise HTTPException(400, f"Unknown permission(s): {', '.join(bad)}.")
    return sorted(set(values))


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    users = db.scalars(select(User).order_by(User.is_root.desc(), User.username))
    return {"users": [user_dict(u) for u in users], "permissions": list(PERMISSIONS)}


@router.post("/users")
def create_user(body: CreateUser, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    name = body.username.strip()
    if problem := username_problem(name) or password_problem(body.password):
        raise HTTPException(400, problem)
    if db.scalar(select(User).where(func.lower(User.username) == name.lower())):
        raise HTTPException(409, "Username is taken.")
    user = User(
        username=name,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        permissions=_perms(body.permissions),
    )
    db.add(user)
    db.flush()
    return {"user": user_dict(user)}


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, body: UpdateUser, db: Session = Depends(get_db), me: User = Depends(admin_user)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    if user.is_root and not me.is_root:
        raise HTTPException(403, "Only `admin` can change the `admin` account.")
    if body.is_admin is not None:
        if user.is_root:
            raise HTTPException(400, "`admin` is always an admin.")
        user.is_admin = body.is_admin
    if body.permissions is not None:
        user.permissions = _perms(body.permissions)
    if body.password:
        if problem := password_problem(body.password):
            raise HTTPException(400, problem)
        user.password_hash = hash_password(body.password)
        if user.id != me.id:
            db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    return {"user": user_dict(user)}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), me: User = Depends(admin_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    if user.is_root:
        raise HTTPException(400, "The `admin` account cannot be deleted.")
    if user.id == me.id:
        raise HTTPException(400, "You cannot delete your own account here.")
    db.delete(user)
    return {"ok": True}


@router.get("/settings")
def get_settings_(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return {"registration_enabled": bool(get_app_setting(db, "registration_enabled"))}


@router.put("/settings")
def put_settings(body: AppSettingsBody, db: Session = Depends(get_db), _: User = Depends(admin_user)):
    set_app_setting(db, "registration_enabled", body.registration_enabled)
    return {"registration_enabled": body.registration_enabled}
