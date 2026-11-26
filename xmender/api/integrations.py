"""Gmail, Discord webhook and Anthropic integrations.

Every save runs a live check first; nothing is stored unless it passes. The
only exception is the Discord test, which posts a real message and can
therefore be skipped explicitly.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Integration, Task, User
from ..security import decrypt, encrypt
from ..services import discord, gmail, llm, pipeline
from ..services.accounts import gmail_account
from .deps import require

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

DISCORD_TEST_TEXT = (
    "This is a test message from xMender. If you can read this, the webhook works "
    "and xMender notifications will appear here."
)


def _gmail_dict(i: Integration) -> dict[str, Any]:
    c, s = i.config, i.state or {}
    return {
        "id": i.id,
        "name": i.name,
        "email": c.get("email"),
        "display_name": c.get("display_name") or "",
        "from_name": c.get("display_name") or c.get("email"),
        "smtp_enabled": bool(c.get("smtp_enabled")),
        "imap_host": c.get("imap_host"),
        "imap_port": c.get("imap_port"),
        "smtp_host": c.get("smtp_host"),
        "smtp_port": c.get("smtp_port"),
        "last_polled_at": s.get("last_polled_at"),
        "last_error": s.get("last_error"),
        "pending": s.get("pending", 0),
    }


def _discord_dict(i: Integration) -> dict[str, Any]:
    try:
        hook = discord.parse_webhook_url(decrypt(i.secret))
        hint = f"discord.com/api/webhooks/{hook.id}/••••" + (
            f" (thread {hook.thread_id})" if hook.thread_id else ""
        )
    except Exception:
        hint = "(unreadable)"
    return {"id": i.id, "name": i.name, "url_hint": hint}


def _anthropic_dict(i: Integration) -> dict[str, Any]:
    return {"id": i.id, "key_hint": i.config.get("key_hint", "")}


def _owned(db: Session, user: User, integration_id: int, kind: str | None = None) -> Integration:
    integ = db.get(Integration, integration_id)
    if integ is None or integ.user_id != user.id or (kind and integ.kind != kind):
        raise HTTPException(404, "Integration not found.")
    return integ


@router.get("")
def list_integrations(db: Session = Depends(get_db), user: User = Depends(require("integrations"))):
    rows = list(
        db.scalars(select(Integration).where(Integration.user_id == user.id).order_by(Integration.id))
    )
    anth = next((r for r in rows if r.kind == "anthropic"), None)
    return {
        "gmail": [_gmail_dict(r) for r in rows if r.kind == "gmail"],
        "discord": [_discord_dict(r) for r in rows if r.kind == "discord"],
        "anthropic": _anthropic_dict(anth) if anth else None,
        "defaults": {
            "imap_host": gmail.IMAP_HOST,
            "imap_port": gmail.IMAP_PORT,
            "smtp_host": gmail.SMTP_HOST,
            "smtp_port": gmail.SMTP_PORT,
            "app_passwords_url": gmail.APP_PASSWORDS_URL,
        },
    }


# --- Gmail -------------------------------------------------------------------


class GmailBody(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=128)
    email: str
    display_name: str = Field(default="", max_length=128)
    password: str | None = None  # blank on edit keeps the stored one
    smtp_enabled: bool = False
    imap_host: str = gmail.IMAP_HOST
    imap_port: int = Field(default=gmail.IMAP_PORT, ge=1, le=65535)
    smtp_host: str = gmail.SMTP_HOST
    smtp_port: int = Field(default=gmail.SMTP_PORT, ge=1, le=65535)
    save: bool = True


async def _check_gmail(acct: gmail.Account, smtp: bool) -> tuple[int, int]:
    try:
        cursor = await asyncio.to_thread(gmail.test_imap, acct)
        if smtp:
            await asyncio.to_thread(gmail.test_smtp, acct)
    except gmail.GmailError as e:
        raise HTTPException(400, str(e)) from e
    return cursor


@router.post("/gmail")
async def save_gmail(body: GmailBody, db: Session = Depends(get_db), user: User = Depends(require("integrations"))):
    try:
        address = gmail.normalize_gmail(body.email)
    except gmail.GmailError as e:
        raise HTTPException(400, str(e)) from e

    existing = _owned(db, user, body.id, "gmail") if body.id else None
    others = db.scalars(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.kind == "gmail",
            Integration.id != (body.id or 0),
        )
    )
    if any(o.config.get("email") == address for o in others):
        raise HTTPException(409, "This Gmail address is already connected.")

    if body.password and body.password.strip():
        try:
            password = gmail.normalize_app_password(body.password)
        except gmail.GmailError as e:
            raise HTTPException(400, str(e)) from e
    elif existing is not None:
        password = decrypt(existing.secret)
    else:
        raise HTTPException(400, "App password is required.")

    acct = gmail.Account(
        email=address,
        password=password,
        imap_host=body.imap_host.strip() or gmail.IMAP_HOST,
        imap_port=body.imap_port,
        smtp_host=body.smtp_host.strip() or gmail.SMTP_HOST,
        smtp_port=body.smtp_port,
    )
    # SMTP is checked whenever it will be enabled, even if sending stays off
    # later; that way toggling it on afterwards rarely fails.
    uidvalidity, last_uid = await _check_gmail(acct, body.smtp_enabled)
    if not body.save:
        return {"ok": True, "tested": ["imap"] + (["smtp"] if body.smtp_enabled else [])}

    config = {
        "email": address,
        "display_name": body.display_name.strip(),
        "smtp_enabled": body.smtp_enabled,
        "imap_host": acct.imap_host,
        "imap_port": acct.imap_port,
        "smtp_host": acct.smtp_host,
        "smtp_port": acct.smtp_port,
    }
    if existing is None:
        integ = Integration(
            user_id=user.id,
            kind="gmail",
            name=body.name.strip(),
            config=config,
            secret=encrypt(password),
            # Start from "now": only mail arriving after setup is processed.
            state={"uidvalidity": uidvalidity, "last_uid": last_uid},
        )
        db.add(integ)
    else:
        integ = existing
        if existing.config.get("email") != address:
            integ.state = {"uidvalidity": uidvalidity, "last_uid": last_uid}
        integ.name = body.name.strip()
        integ.config = config
        integ.secret = encrypt(password)
    db.flush()
    return {"integration": _gmail_dict(integ)}


class SmtpToggle(BaseModel):
    enabled: bool


@router.patch("/gmail/{integration_id}/smtp")
async def toggle_smtp(
    integration_id: int, body: SmtpToggle, db: Session = Depends(get_db), user: User = Depends(require("integrations"))
):
    integ = _owned(db, user, integration_id, "gmail")
    if body.enabled:
        try:
            await asyncio.to_thread(gmail.test_smtp, gmail_account(integ))
        except gmail.GmailError as e:
            raise HTTPException(400, str(e)) from e
    integ.config = {**integ.config, "smtp_enabled": body.enabled}
    return {"integration": _gmail_dict(integ)}


# --- Discord -----------------------------------------------------------------


class DiscordBody(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=128)
    url: str | None = None  # blank on edit keeps the stored one
    test: Literal["send", "skip"]


@router.post("/discord")
async def save_discord(body: DiscordBody, db: Session = Depends(get_db), user: User = Depends(require("integrations"))):
    existing = _owned(db, user, body.id, "discord") if body.id else None
    if body.url and body.url.strip():
        try:
            url = discord.canonical_url(discord.parse_webhook_url(body.url))
        except discord.DiscordError as e:
            raise HTTPException(400, str(e)) from e
    elif existing is not None:
        url = decrypt(existing.secret)
    else:
        raise HTTPException(400, "Webhook URL is required.")

    name = body.name.strip()
    if body.test == "send":
        try:
            await asyncio.to_thread(
                discord.send_embed, url, description=DISCORD_TEST_TEXT,
                thread_name="xMender test",
            )
        except discord.DiscordError as e:
            raise HTTPException(400, str(e)) from e

    if existing is None:
        integ = Integration(user_id=user.id, kind="discord", name=name, config={}, secret=encrypt(url), state={})
        db.add(integ)
    else:
        integ = existing
        integ.name = name
        integ.secret = encrypt(url)
    db.flush()
    return {"integration": _discord_dict(integ), "tested": body.test == "send"}


# --- Anthropic ---------------------------------------------------------------


class AnthropicBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


@router.post("/anthropic")
async def save_anthropic(body: AnthropicBody, db: Session = Depends(get_db), user: User = Depends(require("integrations"))):
    key = body.api_key.strip()
    try:
        models = await asyncio.to_thread(llm.list_models, key, refresh=True)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if not models:
        raise HTTPException(400, "The API key works but no models are available to it.")

    hint = f"{key[:7]}…{key[-4:]}" if len(key) > 12 else "••••"
    integ = db.scalar(
        select(Integration).where(Integration.user_id == user.id, Integration.kind == "anthropic")
    )
    if integ is None:
        integ = Integration(
            user_id=user.id, kind="anthropic", name="Anthropic", config={"key_hint": hint},
            secret=encrypt(key), state={},
        )
        db.add(integ)
    else:
        integ.config = {"key_hint": hint}
        integ.secret = encrypt(key)
    # Drop a default model the new key cannot use.
    ids = {m.id for m in models}
    if user.default_model not in ids:
        user.default_model = None
    db.flush()
    return {"integration": _anthropic_dict(integ), "model_count": len(models)}


# --- Delete ------------------------------------------------------------------


@router.delete("/{integration_id}")
def delete_integration(integration_id: int, db: Session = Depends(get_db), user: User = Depends(require("integrations"))):
    integ = _owned(db, user, integration_id)
    tasks = list(db.scalars(select(Task).where(Task.user_id == user.id)))
    if integ.kind == "gmail":
        using = [t.name for t in tasks if t.gmail_integration_id == integ.id]
    else:
        using = [t.name for t in tasks if integ.id in pipeline.step_refs(t.steps)]
    if using:
        raise HTTPException(409, f"Still used by task(s): {', '.join(using)}. Change or delete those first.")
    db.delete(integ)
    return {"ok": True}
