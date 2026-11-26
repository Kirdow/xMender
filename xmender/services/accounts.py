"""Helpers turning stored integrations into usable credentials."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Integration, User
from ..security import decrypt
from . import gmail
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


def anthropic_key(db: Session, user_id: int) -> str | None:
    integ = db.scalar(
        select(Integration).where(Integration.user_id == user_id, Integration.kind == "anthropic")
    )
    return decrypt(integ.secret) if integ else None


def discord_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Integration.id).where(
                Integration.user_id == user_id, Integration.kind == "discord"
            )
        )
    )


def run_context(db: Session, user: User) -> RunContext:
    hooks = db.scalars(
        select(Integration).where(Integration.user_id == user.id, Integration.kind == "discord")
    )
    return RunContext(
        api_key=anthropic_key(db, user.id),
        default_model=user.default_model,
        discord={h.id: (h.name, decrypt(h.secret)) for h in hooks},
        timezone=user.timezone,
    )
