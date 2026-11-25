"""Recording and summarising Anthropic API usage and cost."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApiUsage, as_utc
from . import llm, pricing

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "cache_read_tokens",
)


def record(
    db: Session,
    user_id: int,
    attempts: Iterable[tuple[str, llm.UsageAttempt]],
    *,
    task_id: int | None = None,
    task_name: str = "",
    email_id: int | None = None,
) -> int:
    """Add one `ApiUsage` row per attempt. Returns the number of rows."""
    n = 0
    for source, a in attempts:
        t = a.tokens
        db.add(
            ApiUsage(
                user_id=user_id,
                model=a.model[:128],
                kind=a.kind,
                source=source[:32],
                task_id=task_id,
                task_name=task_name[:128],
                email_id=email_id,
                input_tokens=t.input,
                output_tokens=t.output,
                cache_write_5m_tokens=t.cache_write_5m,
                cache_write_1h_tokens=t.cache_write_1h,
                cache_read_tokens=t.cache_read,
                inference_geo=(a.inference_geo or None) and a.inference_geo[:16],
                billed=a.billed,
                cost_nanousd=a.cost_nanos(),
            )
        )
        n += 1
    return n


def resolve_tz(name: str | None) -> tzinfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def period_start(period: str, now: datetime, tz: tzinfo) -> datetime | None:
    """Start of a reporting period in the viewer's time zone, or None for all."""
    local = now.astimezone(tz)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return midnight
    if period == "7d":
        return midnight - timedelta(days=6)
    if period == "30d":
        return midnight - timedelta(days=29)
    if period == "month":
        return midnight.replace(day=1)
    return None


def _blank() -> dict[str, Any]:
    return {"requests": 0, **{f: 0 for f in TOKEN_FIELDS}, "cost_nanousd": 0, "unpriced": 0}


def _add(acc: dict[str, Any], row: ApiUsage) -> None:
    acc["requests"] += 1
    for f in TOKEN_FIELDS:
        acc[f] += getattr(row, f) or 0
    if row.cost_nanousd is None:
        acc["unpriced"] += 1
    else:
        acc["cost_nanousd"] += row.cost_nanousd


def summarize(
    db: Session, user_id: int | None, *, since: datetime | None, tz: tzinfo
) -> dict[str, Any]:
    """Totals, per-model, per-task and per-day breakdowns. `user_id=None`
    covers every user."""
    q = select(ApiUsage)
    if user_id is not None:
        q = q.where(ApiUsage.user_id == user_id)
    if since is not None:
        # SQLite drops tzinfo and compares text, so compare in UTC like storage.
        q = q.where(ApiUsage.created_at >= since.astimezone(UTC))
    total = _blank()
    models: dict[str, dict[str, Any]] = {}
    tasks: dict[str, dict[str, Any]] = {}
    days: dict[str, dict[str, Any]] = {}
    first: datetime | None = None
    for row in db.scalars(q.order_by(ApiUsage.id)):
        created = as_utc(row.created_at)
        if first is None or created < first:
            first = created
        _add(total, row)
        _add(models.setdefault(row.model, _blank()), row)
        _add(tasks.setdefault(row.task_name or "(unnamed)", _blank()), row)
        _add(days.setdefault(created.astimezone(tz).date().isoformat(), _blank()), row)

    model_rows = []
    for model_id, acc in sorted(models.items(), key=lambda kv: -kv[1]["cost_nanousd"]):
        p = pricing.lookup(model_id)
        model_rows.append({"model": model_id, **acc, "rates": p.rates.as_dict() if p else None})
    return {
        "total": total,
        "models": model_rows,
        "tasks": [
            {"task": k, **v}
            for k, v in sorted(tasks.items(), key=lambda kv: -kv[1]["cost_nanousd"])
        ],
        "days": [{"day": k, **v} for k, v in sorted(days.items(), reverse=True)],
        "first_at": first.isoformat() if first else None,
        "prices_as_of": pricing.PRICES_AS_OF,
        "pricing_url": pricing.PRICING_URL,
    }
