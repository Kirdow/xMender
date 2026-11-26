"""Helpers turning stored integrations into usable credentials."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Integration, User
from ..security import decrypt
from . import gmail, http_hook
from .pipeline import RunContext


def gmail_account(integ: Integration) -> gmail.Account:
    c = integ.config
    return gmail.Account(
        email=c["email"],
        password=decrypt(integ.secret),
        imap_host=c.get("imap_host", gmail.IMAP_HOST),
        imap_port=int(c.get("imap_port", gmail.IMAP_PORT)),
        smtp_host=c.get("smtp_host", gmail.SMTP_HOST),
        smtp_port=int(c.get("smtp_port", gmail.SMTP_PORT)),
    )


def http_target(integ: Integration) -> http_hook.Target:
    data = json.loads(decrypt(integ.secret))
    return http_hook.Target(url=data["url"], headers=data.get("headers") or {})


def anthropic_key(db: Session, user_id: int) -> str | None:
    integ = db.scalar(
        select(Integration).where(Integration.user_id == user_id, Integration.kind == "anthropic")
    )
    return decrypt(integ.secret) if integ else None


def _ids(db: Session, user_id: int, kind: str) -> set[int]:
    return set(
        db.scalars(
            select(Integration.id).where(Integration.user_id == user_id, Integration.kind == kind)
        )
    )


def discord_ids(db: Session, user_id: int) -> set[int]:
    return _ids(db, user_id, "discord")


def http_ids(db: Session, user_id: int) -> set[int]:
    return _ids(db, user_id, "http")


def run_context(db: Session, user: User) -> RunContext:
    rows = list(db.scalars(
        select(Integration).where(
            Integration.user_id == user.id, Integration.kind.in_(("discord", "http"))
        )
    ))
    return RunContext(
        api_key=anthropic_key(db, user.id),
        default_model=user.default_model,
        discord={h.id: (h.name, decrypt(h.secret)) for h in rows if h.kind == "discord"},
        timezone=user.timezone,
        http={
            h.id: (h.name, http_target(h), h.config.get("method", "POST"))
            for h in rows if h.kind == "http"
        },
        http_allow_private=get_settings().http_allow_private,
    )
