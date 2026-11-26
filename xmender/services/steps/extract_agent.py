"""Extract (Agent): the model fills user-defined fields as JSON.

Structured outputs enforce the schema when the model supports them; the
result is validated and coerced here either way.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from .. import llm, prompts
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext,
    call_llm, clip, validate_instructions, validate_model,
)

FIELD_TYPES = ("string", "number", "integer", "boolean", "date")
FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
RESERVED_FIELDS = {"matched"}
MAX_FIELDS = 20
VALUE_LIMIT = 2000


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("fields")
    if not isinstance(raw, list) or not raw:
        raise StepConfigError("add at least one field to extract.")
    if len(raw) > MAX_FIELDS:
        raise StepConfigError(f"at most {MAX_FIELDS} fields.")
    fields, seen = [], set()
    for f in raw:
        if not isinstance(f, dict):
            raise StepConfigError("invalid field.")
        name = str(f.get("name") or "").strip().lower()
        if not FIELD_NAME_RE.match(name) or name in RESERVED_FIELDS:
            raise StepConfigError(
                f"field name `{name}` must start with a letter and use only a-z, 0-9 and _."
            )
        if name in seen:
            raise StepConfigError(f"field `{name}` is listed twice.")
        seen.add(name)
        ftype = f.get("type") if f.get("type") in FIELD_TYPES else "string"
        fields.append({
            "name": name,
            "type": ftype,
            "description": str(f.get("description") or "").strip()[:300],
            "required": f.get("required") is True,
        })
    return {
        "fields": fields,
        "instructions": validate_instructions(cfg, 4000, required=False),
        "model": validate_model(cfg, vctx),
    }


def output_schema(fields: list[dict[str, Any]]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for f in fields:
        base: dict[str, Any] = (
            {"type": "string", "format": "date"} if f["type"] == "date" else {"type": f["type"]}
        )
        prop: dict[str, Any] = {"anyOf": [base, {"type": "null"}]}
        if f.get("description"):
            prop["description"] = f["description"]
        props[f["name"]] = prop
    return {
        "type": "object",
        "properties": props,
        "required": [f["name"] for f in fields],
        "additionalProperties": False,
    }


def parse_json(text: str) -> dict[str, Any]:
    """The first JSON object in `text` (tolerates code fences and prose)."""
    s = text.strip()
    try:
        data = json.loads(s)
    except ValueError:
        start = s.find("{")
        if start < 0:
            raise StepError("The model did not return JSON.") from None
        try:
            data, _ = json.JSONDecoder().raw_decode(s[start:])
        except ValueError:
            raise StepError("The model returned invalid JSON.") from None
    if not isinstance(data, dict):
        raise StepError("The model did not return a JSON object.")
    return data


def coerce(ftype: str, v: Any) -> Any:
    """Coerce a value to the field type; None if it does not fit."""
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v.lower() in ("null", "none", "n/a"):
            return None
    if ftype == "string":
        return clip(v if isinstance(v, str) else json.dumps(v), VALUE_LIMIT)
    if ftype == "boolean":
        if isinstance(v, bool):
            return v
        return {"true": True, "yes": True, "false": False, "no": False}.get(str(v).lower())
    if ftype in ("number", "integer"):
        if isinstance(v, bool):
            return None
        if isinstance(v, str):
            v = re.sub(r"[^\d.\-]", "", v.replace(",", ""))
        try:
            num = float(v)
        except (TypeError, ValueError):
            return None
        if ftype == "integer":
            return int(num) if num.is_integer() else None
        return int(num) if num.is_integer() else num
    if ftype == "date":
        try:
            return date.fromisoformat(str(v)[:10]).isoformat()
        except ValueError:
            return None
    return None


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    fields = cfg["fields"]
    prompt = prompts.extract_agent_prompt(cfg.get("instructions") or "", fields, mail)
    res = call_llm(ctx, cfg, prompt, entry, state, output_schema=output_schema(fields))
    entry.update(model=res.model, response=clip(res.text))
    if res.stop_reason == "refusal":
        raise llm.LLMError("Model declined to extract from this email.")
    if res.stop_reason == "max_tokens":
        raise StepError("The model's answer was cut off (max_tokens).")
    data = parse_json(res.text)
    values = {f["name"]: coerce(f["type"], data.get(f["name"])) for f in fields}
    entry["response"] = clip(json.dumps(values, ensure_ascii=False, indent=1))
    missing = [f["name"] for f in fields if f["required"] and values[f["name"]] is None]
    if missing:
        raise StepError(f"Required field(s) not found: {', '.join(missing)}.")
    found = sum(v is not None for v in values.values())
    detail = f"extracted {found} of {len(fields)} field(s)"
    if not res.structured:
        detail += " (model without structured outputs; validated here)"
    return Result(outcome="pass", detail=detail, vars=values)


STEP = StepDef(
    type="extract_agent", label="Extract (Agent)", group="agent",
    validate=_validate, run=_run, uses_llm=True,
    outputs=lambda cfg: [f["name"] for f in cfg.get("fields") or []],
)
