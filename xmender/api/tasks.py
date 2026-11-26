"""Tasks: ordered step chains run on each new email."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..masking import mask_email
from ..models import Integration, Task, User
from ..services import chains, gmail, llm, pipeline, signals
from ..services.accounts import anthropic_key, discord_ids, http_ids
from .deps import require

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    gmail_integration_id: int
    enabled: bool = True
    steps: list[dict[str, Any]]
    # {"task_id": int, "status": [...]} to run only after another task.
    depends_on: dict[str, Any] | None = None


def _task_dict(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "enabled": t.enabled,
        "gmail_integration_id": t.gmail_integration_id,
        "steps": t.steps,
        "depends_on": (
            {"task_id": t.depends_on_id, "status": t.depends_on_status or chains.DEFAULT_STATUSES}
            if t.depends_on_id else None
        ),
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
            {"id": r.id, "name": r.name, **({"email": mask_email(r.config.get("email"))} if r.kind == "gmail" else {})}
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
        "chain_statuses": [{"key": k, "label": v} for k, v in chains.STATUS_LABELS.items()],
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    tasks = db.scalars(select(Task).where(Task.user_id == user.id).order_by(Task.id))
    return {"tasks": [_task_dict(t) for t in tasks]}


@dataclass
class _Valid:
    steps: list[dict[str, Any]]
    parent_id: int | None
    statuses: list[str] | None


async def _validated(db: Session, user: User, body: TaskBody, task_id: int | None = None) -> _Valid:
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
    nodes = {t.id: chains.node(t) for t in db.scalars(select(Task).where(Task.user_id == user.id))}
    dids, hids = discord_ids(db, user.id), http_ids(db, user.id)
    try:
        parent_id, statuses = chains.validate(body.depends_on, task_id, body.gmail_integration_id, nodes)
        steps = pipeline.validate_steps(
            body.steps, discord_ids=dids, model_ids=model_ids, http_ids=hids,
            inherited=chains.inherited_outputs(parent_id, nodes),
        )
    except pipeline.StepConfigError as e:
        raise HTTPException(400, str(e)) from e
    if task_id is not None:
        _check_dependents(nodes, chains.Node(
            id=task_id, name=body.name.strip(), inbox_id=body.gmail_integration_id, steps=steps,
            parent_id=parent_id, statuses=statuses or chains.DEFAULT_STATUSES,
        ), dids, hids)
    agent_steps = pipeline.llm_steps(steps)
    if agent_steps and not key:
        raise HTTPException(400, "Agent steps need the Anthropic integration set up first.")
    if not user.default_model and any(not s["config"].get("model") for s in agent_steps):
        raise HTTPException(400, "Pick a model for each agent step, or set a default model in Settings.")
    return _Valid(steps, parent_id, statuses)


def _check_dependents(
    nodes: dict[int, chains.Node], new: chains.Node, dids: set[int], hids: set[int],
) -> None:
    """Refuse an edit that would break tasks chained after this one."""
    nodes = {**nodes, new.id: new}
    for child in chains.descendants(new.id, nodes):
        if child.inbox_id != new.inbox_id:
            raise HTTPException(400, f"“{child.name}” runs after this task, so it must keep the same inbox.")
        try:
            pipeline.validate_steps(
                child.steps, discord_ids=dids, model_ids=None, http_ids=hids,
                inherited=chains.inherited_outputs(child.parent_id, nodes),
            )
        except pipeline.StepConfigError as e:
            raise HTTPException(
                400, f"“{child.name}” runs after this task and uses its step names. "
                     f"This change would break it: {e}",
            ) from e


@router.post("")
async def create_task(body: TaskBody, db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    v = await _validated(db, user, body)
    task = Task(
        user_id=user.id,
        gmail_integration_id=body.gmail_integration_id,
        name=body.name.strip(),
        enabled=body.enabled,
        steps=v.steps,
        depends_on_id=v.parent_id,
        depends_on_status=v.statuses,
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
    v = await _validated(db, user, body, task.id)
    task.name = body.name.strip()
    task.gmail_integration_id = body.gmail_integration_id
    task.enabled = body.enabled
    task.steps = v.steps
    task.depends_on_id = v.parent_id
    task.depends_on_status = v.statuses
    db.flush()
    return {"task": _task_dict(task)}


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(require("tasks"))):
    task = _owned(db, user, task_id)
    child = db.scalars(select(Task).where(Task.depends_on_id == task.id).limit(1)).first()
    if child is not None:
        raise HTTPException(409, f"“{child.name}” runs after this task. Change or delete it first.")
    db.delete(task)
    return {"ok": True}
