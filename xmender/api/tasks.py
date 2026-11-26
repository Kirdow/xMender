"""Tasks: ordered step chains run on each new email."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Integration, Task, User
from ..services import gmail, llm, pipeline, signals
from ..services.accounts import anthropic_key, discord_ids, http_ids
from .deps import require

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    gmail_integration_id: int
    enabled: bool = True
    steps: list[dict[str, Any]]


def _task_dict(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "enabled": t.enabled,
        "gmail_integration_id": t.gmail_integration_id,
        "steps": t.steps,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("/meta")
def meta(db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    rows = db.scalars(
        select(Integration).where(Integration.user_id == user.id, Integration.kind.in_(("gmail", "discord", "http")))
    )
    gm, dc, hp = [], [], []
    for r in rows:
        {"gmail": gm, "discord": dc, "http": hp}[r.kind].append(
            {"id": r.id, "name": r.name, **({"email": r.config.get("email")} if r.kind == "gmail" else {})}
        )
    return {
        "step_types": pipeline.step_types_meta(),
        "gmail": gm,
        "discord": dc,
        "http": hp,
        "has_anthropic": anthropic_key(db, user.id) is not None,
        "default_model": user.default_model,
        "bulk_kinds": [{"key": k, "label": v} for k, v in signals.BULK_KINDS.items()],
        "gmail_categories": list(gmail.CATEGORIES),
        "phishing_kinds": [{"key": k, "label": v} for k, v in signals.PHISHING_KINDS.items()],
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    tasks = db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.id))
    return {"tasks": [_task_dict(t) for t in tasks]}


async def _validated(db: Session, user: User, body: TaskBody) -> list[dict[str, Any]]:
    integ = db.get(Integration, body.gmail_integration_id)
    if integ is None or integ.user_id != user.id or integ.kind != "gmail":
        raise HTTPException(400, "Pick a Gmail inbox for this task.")
    model_ids: set[str] | None = None
    key = anthropic_key(db, user.id)
    if key:
        try:
            model_ids = {m.id for m in await asyncio.to_thread(llm.list_models, key)}
        except llm.LLMError:
            model_ids = None
    try:
        steps = pipeline.validate_steps(
            body.steps, discord_ids=discord_ids(db, user.id), model_ids=model_ids,
            http_ids=http_ids(db, user.id),
        )
    except pipeline.StepConfigError as e:
        raise HTTPException(400, str(e)) from e
    agent_steps = pipeline.llm_steps(steps)
    if agent_steps and not key:
        raise HTTPException(400, "Agent steps need the Anthropic integration set up first.")
    if not user.default_model and any(not s["config"].get("model") for s in agent_steps):
        raise HTTPException(400, "Pick a model for each agent step, or set a default model in Settings.")
    return steps


@router.post("")
async def create_task(body: TaskBody, db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    steps = await _validated(db, user, body)
    task = Task(
        user_id=user.id,
        gmail_integration_id=body.gmail_integration_id,
        name=body.name.strip(),
        enabled=body.enabled,
        steps=steps,
    )
    db.add(task)
    db.flush()
    return {"task": _task_dict(task)}


def _owned(db: Session, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found.")
    return task


@router.put("/{task_id}")
async def update_task(task_id: int, body: TaskBody, db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    task = _owned(db, user, task_id)
    steps = await _validated(db, user, body)
    task.name = body.name.strip()
    task.gmail_integration_id = body.gmail_integration_id
    task.enabled = body.enabled
    task.steps = steps
    db.flush()
    return {"task": _task_dict(task)}


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    db.delete(_owned(db, user, task_id))
    return {"ok": True}
