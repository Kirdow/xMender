"""HTTP webhook: POST/PUT a templated JSON or text body to an HTTP integration.

JSON mode: the template must be valid JSON. Placeholders are filled only
inside string values, so email text can never break the JSON. A string that
is exactly one placeholder without modifiers (`"{{extract.amount}}"`) keeps
the value's own type (number, true/false, null).
"""

from __future__ import annotations

import json
from typing import Any

from .. import http_hook, template
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext, clip,
)

DEFAULT_JSON = (
    '{\n  "subject": "{{email.subject}}",\n  "from": "{{email.from_addr}}",\n'
    '  "snippet": "{{email.snippet}}"\n}'
)
BODY_LIMIT = 8000


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in (_strings(k) + _strings(v))]
    return []


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    try:
        hid = int(cfg.get("http_integration_id"))
    except (TypeError, ValueError):
        hid = None
    if hid not in vctx.http_ids:
        raise StepConfigError("pick an HTTP webhook.")
    mode = cfg.get("mode") if cfg.get("mode") in ("json", "text") else "json"
    body = str(cfg.get("body") or "").strip()
    if not body:
        raise StepConfigError("the body is empty.")
    if len(body) > BODY_LIMIT:
        raise StepConfigError(f"the body is too long (at most {BODY_LIMIT} characters).")
    try:
        if mode == "json":
            try:
                parsed = json.loads(body)
            except ValueError as e:
                raise StepConfigError(
                    f"the body is not valid JSON ({e.msg}, line {e.lineno}). Put placeholders "
                    'inside quotes, e.g. "{{email.subject}}".'
                ) from e
            for text in _strings(parsed):
                template.check(text, vctx.outputs)
        else:
            template.check(body, vctx.outputs)
    except template.TemplateError as e:
        raise StepConfigError(f"body: {e}") from e
    return {"http_integration_id": hid, "mode": mode, "body": body}


def _render_json(node: Any, scope: dict[str, dict[str, Any]], warnings: list[str]) -> Any:
    if isinstance(node, str):
        ph = template.parse(node)
        if len(ph) == 1 and ph[0].raw == node.strip() and not ph[0].mods:
            ns = scope.get(ph[0].ns)
            if ns is None or ph[0].field not in ns:
                warnings.append(f"{ph[0].ns}.{ph[0].field} had no value")
                return None
            value = ns[ph[0].field]
            return value if value is None or isinstance(value, (bool, int, float)) else template.to_text(value)
        text, w = template.render(node, scope)
        warnings += w
        return text
    if isinstance(node, list):
        return [_render_json(v, scope, warnings) for v in node]
    if isinstance(node, dict):
        return {_render_json(k, scope, warnings): _render_json(v, scope, warnings) for k, v in node.items()}
    return node


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    hook = ctx.http.get(cfg.get("http_integration_id"))
    if hook is None:
        raise StepError("The HTTP webhook for this step was removed.")
    name, target, method = hook
    scope = template.scope_for(mail, state.vars)
    warnings: list[str] = []
    if cfg.get("mode") == "text":
        body, warnings = template.render(cfg["body"], scope)
        preview = body
    else:
        body = _render_json(json.loads(cfg["body"]), scope, warnings)
        preview = json.dumps(body, ensure_ascii=False, indent=1)
    if warnings:
        entry["warning"] = "; ".join(dict.fromkeys(warnings))
    entry["response"] = clip(preview)
    try:
        status = http_hook.send(target, method=method, content_type=cfg.get("mode") or "json",
                                body=body, allow_private=ctx.http_allow_private)
    except http_hook.HttpHookError as e:
        raise StepError(str(e)) from e
    return Result(outcome="sent", detail=f"{method} to {name}: HTTP {status}", vars={"status": status})


def _refs(cfg: dict[str, Any]) -> set[int]:
    hid = cfg.get("http_integration_id")
    return {hid} if isinstance(hid, int) else set()


STEP = StepDef(
    type="http_post", label="HTTP webhook", group="action",
    validate=_validate, run=_run, refs=_refs, outputs=lambda cfg: ["status"],
)
