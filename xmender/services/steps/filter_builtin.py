"""Filter (Built-in): Gmail-like criteria, no LLM."""

from __future__ import annotations

from typing import Any

from .. import filters
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext,
)


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    try:
        norm = filters.normalize_config(cfg)
    except ValueError as e:
        raise StepConfigError(str(e)) from e
    if filters.is_empty(norm):
        raise StepConfigError("set at least one filter criterion.")
    return norm


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    try:
        ok, reason = filters.matches(cfg, mail)
    except filters.FilterError as e:
        raise StepError(str(e)) from e
    return Result(matched=ok, detail=reason)


STEP = StepDef(
    type="filter_builtin", label="Filter (Built-in)", group="filter",
    validate=_validate, run=_run,
)
