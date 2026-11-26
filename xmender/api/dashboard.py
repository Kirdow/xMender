"""Activity feed, manual refresh, model list and personal settings."""

from __future__ import annotations

import asyncio

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..masking import mask_email
from ..models import Email, Integration, TaskRun, User, utcnow
from ..services import llm, timewindow, usage
from ..services.accounts import anthropic_key
from ..services.poller import poller
from .deps import current_user, user_dict

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(Integration).where(Integration.user_id == user.id, Integration.kind == "gmail")
    )
    return {
        "poll_interval_minutes": get_settings().poll_interval_minutes,
        "inboxes": [
            {
                "id": r.id,
                "name": r.name,
                "email": mask_email(r.config.get("email")),
                "last_polled_at": (r.state or {}).get("last_polled_at"),
                "last_error": (r.state or {}).get("last_error"),
                "pending": (r.state or {}).get("pending", 0),
            }
            for r in rows
        ],
    }


@router.get("/emails")
def emails(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    q = select(Email).where(Email.user_id == user.id)
    if before_id:
        q = q.where(Email.id < before_id)
    rows = list(db.scalars(q.order_by(Email.id.desc()).limit(limit)))
    runs: dict[int, list] = {}
    if rows:
        for r in db.scalars(
            select(TaskRun).where(TaskRun.email_id.in_([e.id for e in rows])).order_by(TaskRun.id)
        ):
            runs.setdefault(r.email_id, []).append(
                {"id": r.id, "task_id": r.task_id, "task_name": r.task_name, "status": r.status, "log": r.log}
            )
    return {
        "emails": [
            {
                "id": e.id,
                "integration_id": e.integration_id,
                "sender": e.sender,
                "subject": e.subject,
                "snippet": e.snippet,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "runs": runs.get(e.id, []),
            }
            for e in rows
        ]
    }


@router.post("/poll")
async def poll_now(user: User = Depends(current_user)):
    results = await poller.poll_user(user.id)
    return {"results": results}


@router.get("/llm/models")
async def models(refresh: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    key = anthropic_key(db, user.id)
    if not key:
        return {"models": [], "default_model": user.default_model, "error": "Set up the Anthropic integration first."}
    try:
        items = await asyncio.to_thread(llm.list_models, key, refresh=refresh)
    except llm.LLMError as e:
        return {"models": [], "default_model": user.default_model, "error": str(e)}
    return {
        "models": [{"id": m.id, "display_name": m.display_name} for m in items],
        "default_model": user.default_model,
    }


class MySettings(BaseModel):
    default_model: str | None = None
    timezone: str | None = Field(None, max_length=64)


@router.put("/me/settings")
async def put_my_settings(body: MySettings, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Updates only the fields present in the body."""
    sent = body.model_fields_set
    if "default_model" in sent:
        model = (body.default_model or "").strip() or None
        if model:
            key = anthropic_key(db, user.id)
            if not key:
                raise HTTPException(400, "Set up the Anthropic integration first.")
            try:
                ids = {m.id for m in await asyncio.to_thread(llm.list_models, key)}
            except llm.LLMError as e:
                raise HTTPException(400, str(e)) from e
            if model not in ids:
                raise HTTPException(400, f"Model `{model}` is not offered by the provider.")
        user.default_model = model
    if "timezone" in sent:
        zone = (body.timezone or "").strip() or None
        if zone and not timewindow.valid_zone(zone):
            raise HTTPException(400, f"Unknown time zone `{zone}`.")
        user.timezone = zone
    return {"user": user_dict(user)}


@router.get("/usage")
def api_usage(
    period: Literal["today", "7d", "30d", "month", "all"] = "30d",
    tz: str | None = Query(None, max_length=64),
    scope: Literal["me", "all"] = "me",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Anthropic token usage and cost, from the usage each call reports."""
    if scope == "all" and not user.has_admin():
        raise HTTPException(403, "Only admins can see usage for all users.")
    zone = usage.resolve_tz(tz)
    since = usage.period_start(period, utcnow(), zone)
    data = usage.summarize(db, None if scope == "all" else user.id, since=since, tz=zone)
    return {**data, "period": period, "since": since.isoformat() if since else None, "scope": scope}
