"""Filter (Agent): the model decides; passes only on a final `FILTER MATCH`."""

from __future__ import annotations

from typing import Any

from .. import prompts
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepDef, ValidateContext, call_llm, clip,
    validate_attachments, validate_instructions, validate_model,
)


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    return validate_attachments(
        cfg, {"instructions": validate_instructions(cfg), "model": validate_model(cfg, vctx)}
    )


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    res = call_llm(ctx, cfg, prompts.filter_agent_prompt(cfg["instructions"], mail), entry, state,
                   mail=mail)
    entry.update(model=res.model, response=clip(res.text))
    if res.stop_reason == "refusal":
        return Result(matched=False, detail="model declined to answer")
    ok = prompts.is_filter_match(res.text)
    return Result(matched=ok, detail="FILTER MATCH" if ok else "no match")


STEP = StepDef(
    type="filter_agent", label="Filter (Agent)", group="filter",
    validate=_validate, run=_run, uses_llm=True,
)
