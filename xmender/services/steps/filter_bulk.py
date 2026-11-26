"""Filter (Newsletter / bulk): matches mailing lists and automated mail."""

from __future__ import annotations

from typing import Any

from .. import signals
from ..gmail import ParsedEmail
from .base import Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("kinds")
    kinds = [k for k in signals.BULK_KINDS if isinstance(raw, list) and k in raw]
    if not kinds:
        raise StepConfigError("pick at least one kind of bulk mail.")
    return {"kinds": kinds}


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    fired = [k for k in signals.bulk_signals(mail) if k in cfg["kinds"]]
    detail = f"bulk signals: {', '.join(fired)}" if fired else "no bulk signals"
    return Result(matched=bool(fired), detail=detail, vars={"signals": ", ".join(fired)})


STEP = StepDef(
    type="filter_bulk", label="Filter (Newsletter / bulk)", group="filter",
    validate=_validate, run=_run, outputs=lambda cfg: ["signals"],
)
