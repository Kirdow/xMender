"""Filter (Time window): matches mail processed inside a weekly window.

Uses the time the email is processed, not its Date header (which the sender
controls).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .. import timewindow
from ..gmail import ParsedEmail
from .base import Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("days")
    days = sorted({d for d in raw if isinstance(d, int) and 0 <= d <= 6}) if isinstance(raw, list) else []
    if not days:
        raise StepConfigError("pick at least one day.")
    try:
        start = timewindow.parse_hhmm(cfg.get("start") or "00:00")
        end = timewindow.parse_hhmm(cfg.get("end") or "00:00")
    except ValueError as e:
        raise StepConfigError(str(e)) from e
    zone = str(cfg.get("timezone") or "").strip()
    if zone and not timewindow.valid_zone(zone):
        raise StepConfigError(f"unknown time zone `{zone}`.")
    return {"days": days, "start": f"{start:%H:%M}", "end": f"{end:%H:%M}", "timezone": zone}


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    zone = cfg.get("timezone") or ctx.timezone or "UTC"
    if not timewindow.valid_zone(zone):
        zone = "UTC"
    if not cfg.get("timezone") and not ctx.timezone:
        entry["warning"] = "no time zone set in Settings; used UTC"
    now = ctx.now or datetime.now(UTC)
    ok, local = timewindow.in_window(
        now, cfg["days"], timewindow.parse_hhmm(cfg["start"]), timewindow.parse_hhmm(cfg["end"]), zone
    )
    window = f"{cfg['start']}-{cfg['end']}"
    return Result(
        matched=ok,
        detail=f"{local} is {'inside' if ok else 'outside'} {window}",
        vars={"local_time": local},
    )


STEP = StepDef(
    type="filter_time", label="Filter (Time window)", group="filter",
    validate=_validate, run=_run, outputs=lambda cfg: ["local_time"],
)
