"""Background IMAP polling and task execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..db import session_scope
from ..models import Email, Integration, Task, TaskRun, User, as_utc, utcnow
from . import gmail, pipeline, usage
from .accounts import gmail_account, run_context

log = logging.getLogger(__name__)

SENDER_HISTORY_LIMIT = 1000


def poll_integration(integration_id: int) -> dict[str, Any]:
    """Fetch new mail for one Gmail integration and run its tasks. Blocking."""
    batch = get_settings().poll_batch_size
    with session_scope() as db:
        integ = db.get(Integration, integration_id)
        if integ is None or integ.kind != "gmail":
            return {"id": integration_id, "error": "integration not found"}
        acct = gmail_account(integ)
        state = dict(integ.state or {})

    summary: dict[str, Any] = {"id": integration_id, "new": 0, "runs": 0, "pending": 0}
    try:
        res = gmail.fetch_new(acct, state.get("uidvalidity"), state.get("last_uid"), batch)
    except gmail.GmailError as e:
        _save_state(integration_id, last_error=str(e))
        summary["error"] = str(e)
        return summary
    except Exception as e:
        log.exception("poll failed for integration %s", integration_id)
        _save_state(integration_id, last_error=f"{type(e).__name__}: {e}")
        summary["error"] = str(e)
        return summary

    if res.reset:
        _save_state(integration_id, uidvalidity=res.uidvalidity, last_uid=res.last_uid, last_error=None)
        summary["reset"] = True
        return summary

    for uid, raw in res.messages:
        summary["runs"] += _process_message(
            integration_id, res.uidvalidity, uid, raw, res.gmail_meta.get(uid)
        )
        summary["new"] += 1
        # Advance the cursor per message so a crash never reprocesses mail.
        _save_state(integration_id, uidvalidity=res.uidvalidity, last_uid=uid)

    summary["pending"] = res.pending
    _save_state(integration_id, last_error=None, last_new=summary["new"], pending=res.pending)
    return summary


def _save_state(integration_id: int, **changes: Any) -> None:
    with session_scope() as db:
        integ = db.get(Integration, integration_id)
        if integ is None:
            return
        state = dict(integ.state or {})
        state.update(changes)
        state["last_polled_at"] = utcnow().isoformat()
        integ.state = state


def _process_message(
    integration_id: int, uidvalidity: int, uid: int, raw: bytes, meta: dict | None = None,
) -> int:
    mail = gmail.parse_email(raw)
    if meta:
        mail.labels = list(meta.get("labels") or [])
        mail.category = meta.get("category")
    with session_scope() as db:
        integ = db.get(Integration, integration_id)
        if integ is None:
            return 0
        user = db.get(User, integ.user_id)
        user_id = integ.user_id
        row = Email(
            user_id=integ.user_id,
            integration_id=integration_id,
            uidvalidity=uidvalidity,
            uid=uid,
            message_id=(mail.message_id or "")[:512] or None,
            sender=mail.sender[:512],
            sender_addr=mail.from_addr[:320],
            recipients=mail.to,
            subject=mail.subject,
            snippet=mail.snippet(),
            sent_at=mail.date,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return 0  # already processed
        email_id = row.id
        tasks = list(
            db.scalars(
                select(Task)
                .where(Task.gmail_integration_id == integration_id, Task.enabled.is_(True))
                .order_by(Task.id)
            )
        )
        ctx = run_context(db, user)
        if mail.from_addr:
            ctx.sender_seen = [
                as_utc(t) for t in db.scalars(
                    select(Email.created_at)
                    .where(Email.integration_id == integration_id,
                           Email.sender_addr == mail.from_addr[:320], Email.id != email_id)
                    .order_by(Email.created_at.desc())
                    .limit(SENDER_HISTORY_LIMIT)
                )
            ]
        jobs = [(t.id, t.name, list(t.steps)) for t in tasks]

    # LLM and webhook calls happen outside any DB transaction.
    for task_id, name, steps in jobs:
        result = pipeline.run_task(steps, mail, ctx)
        with session_scope() as db:
            db.add(
                TaskRun(
                    task_id=task_id,
                    email_id=email_id,
                    task_name=name,
                    status=result.status,
                    log=result.log,
                )
            )
            usage.record(
                db, user_id, result.usage, task_id=task_id, task_name=name, email_id=email_id
            )
    return len(jobs)


class Poller:
    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}
        self._task: asyncio.Task | None = None

    def _lock(self, integration_id: int) -> asyncio.Lock:
        return self._locks.setdefault(integration_id, asyncio.Lock())

    async def poll_one(self, integration_id: int) -> dict[str, Any]:
        async with self._lock(integration_id):
            return await asyncio.to_thread(poll_integration, integration_id)

    async def poll_many(self, ids: list[int]) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*(self.poll_one(i) for i in ids)))

    async def poll_user(self, user_id: int) -> list[dict[str, Any]]:
        with session_scope() as db:
            ids = list(
                db.scalars(
                    select(Integration.id).where(
                        Integration.user_id == user_id, Integration.kind == "gmail"
                    )
                )
            )
        return await self.poll_many(ids)

    async def _loop(self) -> None:
        interval = get_settings().poll_interval_minutes * 60
        while True:
            try:
                with session_scope() as db:
                    ids = list(db.scalars(select(Integration.id).where(Integration.kind == "gmail")))
                for s in await self.poll_many(ids):
                    if s.get("error"):
                        log.warning("poll integration %s: %s", s["id"], s["error"])
                    elif s.get("new"):
                        log.info("poll integration %s: %d new, %d task runs", s["id"], s["new"], s["runs"])
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("poll loop iteration failed")
            await asyncio.sleep(interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="xmender-poller")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


poller = Poller()
