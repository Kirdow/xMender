"""Filter (Sender history): how often this sender has written before.

History covers only mail xMender has processed for this inbox, so it starts
when the inbox was connected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..gmail import ParsedEmail
from .base import Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext

MODES = ("first_time", "seen_before", "frequent")
MAX_DAYS = 3650


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    mode = cfg.get("mode")
    if mode not in MODES:
        raise StepConfigError("pick how the sender should be matched.")
    out: dict[str, Any] = {"mode": mode}
    if mode == "frequent":
        try:
            count = int(cfg.get("count"))
            days = int(cfg.get("days")) if cfg.get("days") not in (None, "") else None
        except (TypeError, ValueError):
            raise StepConfigError("count and days must be whole numbers.") from None
        if not 1 <= count <= 1000:
            raise StepConfigError("count must be between 1 and 1000.")
        if days is not None and not 1 <= days <= MAX_DAYS:
            raise StepConfigError(f"days must be between 1 and {MAX_DAYS}.")
        out.update(count=count, days=days)
    return out


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    seen = ctx.sender_seen
    total = len(seen)
    who = mail.from_addr or "unknown sender"
    out = {"seen_count": total}
    if cfg["mode"] == "first_time":
        return Result(matched=total == 0, vars=out,
                      detail=f"first mail from {who}" if not total else f"{who} wrote {total} time(s) before")
    if cfg["mode"] == "seen_before":
        return Result(matched=total > 0, vars=out,
                      detail=f"{who} wrote {total} time(s) before" if total else f"first mail from {who}")
    days = cfg.get("days")
    if days:
        since = (ctx.now or datetime.now(UTC)) - timedelta(days=days)
        n = sum(1 for t in seen if t >= since)
        span = f"in the last {days} day(s)"
    else:
        n, span = total, "before"
    return Result(matched=n >= cfg["count"], vars=out,
                  detail=f"{who} wrote {n} time(s) {span}; needs {cfg['count']}")


STEP = StepDef(
    type="filter_sender", label="Filter (Sender history)", group="filter",
    validate=_validate, run=_run, outputs=lambda cfg: ["seen_count"],
)
