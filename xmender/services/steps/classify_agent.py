"""Classify (Agent): the model picks one of the user's categories.

Outputs `label` (always one of the categories, or `other`) and `reason`.
Pair it with "run if <name>.label equals ..." on later steps to route mail.
"""

from __future__ import annotations

from typing import Any

from .. import llm, prompts
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext,
    call_llm, clip, validate_instructions, validate_model,
)
from .extract_agent import parse_json

OTHER = "other"
MAX_LABELS = 30


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("labels")
    if not isinstance(raw, list):
        raw = []
    labels, seen = [], set()
    for lb in raw:
        if not isinstance(lb, dict):
            continue
        name = " ".join(str(lb.get("name") or "").split())[:60]
        if not name:
            continue
        key = name.lower()
        if key == OTHER:
            raise StepConfigError('"other" is added automatically; pick another name.')
        if key in seen:
            raise StepConfigError(f"category `{name}` is listed twice.")
        seen.add(key)
        labels.append({"name": name, "description": str(lb.get("description") or "").strip()[:300]})
    if not labels:
        raise StepConfigError("add at least one category.")
    if len(labels) > MAX_LABELS:
        raise StepConfigError(f"at most {MAX_LABELS} categories.")
    return {
        "labels": labels,
        "instructions": validate_instructions(cfg, 4000, required=False),
        "model": validate_model(cfg, vctx),
    }


def output_schema(labels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": [lb["name"] for lb in labels] + [OTHER]},
            "reason": {"type": "string"},
        },
        "required": ["label", "reason"],
        "additionalProperties": False,
    }


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    labels = cfg["labels"]
    prompt = prompts.classify_agent_prompt(cfg.get("instructions") or "", labels, mail)
    res = call_llm(ctx, cfg, prompt, entry, state, output_schema=output_schema(labels))
    entry.update(model=res.model, response=clip(res.text))
    if res.stop_reason == "refusal":
        raise llm.LLMError("Model declined to classify this email.")
    if res.stop_reason == "max_tokens":
        raise StepError("The model's answer was cut off (max_tokens).")
    data = parse_json(res.text)
    by_key = {lb["name"].lower(): lb["name"] for lb in labels}
    picked = " ".join(str(data.get("label") or "").split()).lower()
    label = by_key.get(picked, OTHER)
    reason = clip(" ".join(str(data.get("reason") or "").split()), 500)
    detail = f"label: {label}"
    if picked and picked not in by_key and picked != OTHER:
        detail += f" (model answered `{clip(picked, 60)}`, not a category)"
    return Result(outcome="pass", detail=detail, vars={"label": label, "reason": reason})


STEP = StepDef(
    type="classify_agent", label="Classify (Agent)", group="agent",
    validate=_validate, run=_run, uses_llm=True, outputs=lambda cfg: ["label", "reason"],
)
