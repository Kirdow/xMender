"""Filter (Phishing signals): matches when enough warning signs are present."""

from __future__ import annotations

from typing import Any

from .. import signals
from ..gmail import ParsedEmail
from .base import Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("kinds")
    kinds = [k for k in signals.PHISHING_KINDS if isinstance(raw, list) and k in raw]
    if not kinds:
        raise StepConfigError("pick at least one warning sign.")
    try:
        min_signals = int(cfg.get("min_signals") or 1)
    except (TypeError, ValueError):
        raise StepConfigError("the number of signs must be a whole number.") from None
    if not 1 <= min_signals <= len(kinds):
        raise StepConfigError(f"the number of signs must be between 1 and {len(kinds)}.")
    brands_text = str(cfg.get("brands") or "").strip()[:5000]
    try:
        signals.parse_brands(brands_text)
    except ValueError as e:
        raise StepConfigError(str(e)) from e
    if "brand_mismatch" in kinds and not brands_text:
        raise StepConfigError("add at least one protected name, or untick that sign.")
    return {"kinds": kinds, "min_signals": min_signals, "brands": brands_text}


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    brands = signals.parse_brands(cfg.get("brands") or "")
    fired = [k for k in signals.phishing_signals(mail, brands) if k in cfg["kinds"]]
    need = cfg.get("min_signals", 1)
    detail = (f"{len(fired)} sign(s): {', '.join(fired)}" if fired else "no warning signs") + (
        f"; needs {need}" if need > 1 else "")
    return Result(matched=len(fired) >= need, detail=detail,
                  vars={"signals": ", ".join(fired), "count": len(fired)})


STEP = StepDef(
    type="filter_phishing", label="Filter (Phishing signals)", group="filter",
    validate=_validate, run=_run, outputs=lambda cfg: ["signals", "count"],
)
