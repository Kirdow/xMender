"""Task steps: validation and execution.

A task is a flat list of steps. Besides its own `config`, every step may have:
- `name`: lets later steps refer to its outputs in conditions and templates.
- `when`: run only if a condition on an earlier named step's output holds.
- `on_error`: `stop` (default) or `continue`.
Filters also have `negate` and `on_no_match` (`stop` by default, or
`continue`, which records `matched` and keeps going). Optional keys are stored
only when they differ from the default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import discord, gmail, http_hook, llm
from .gmail import ParsedEmail
from .steps import GROUP_LABELS, REGISTRY
from .steps.base import (  # noqa: F401  (re-exported)
    RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext,
)

STEP_TYPES = {k: d.label for k, d in REGISTRY.items()}
MAX_STEPS = 50

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
RESERVED_NAMES = {"email"}
# Ops that compare against a value, and the ones that take a list.
VALUE_OPS = {"equals", "not_equals", "contains", "in", "not_in"}
LIST_OPS = {"in", "not_in"}
OPS = VALUE_OPS | {"is_set", "is_empty", "matched", "not_matched"}
CONDITION_VALUE_LIMIT = 500

_DOMAIN_ERRORS = (
    llm.LLMError, discord.DiscordError, gmail.GmailError, http_hook.HttpHookError,
    StepConfigError, StepError,
)


# --- validation --------------------------------------------------------------


def step_outputs(step: dict[str, Any]) -> set[str]:
    d = REGISTRY.get(step.get("type"))
    if d is None:
        return set()
    out = set(d.outputs(step.get("config") or {}))
    if d.group == "filter":
        out.add("matched")
    return out


def _validate_when(raw: Any, outputs: dict[str, set[str]]) -> dict[str, Any] | None:
    if raw in (None, {}, ""):
        return None
    if not isinstance(raw, dict):
        raise StepConfigError("invalid run-if condition.")
    ref = str(raw.get("step") or "").strip()
    if not ref:
        return None
    if ref not in outputs:
        raise StepConfigError(f"run-if refers to `{ref}`, which is not a named earlier step.")
    op = raw.get("op")
    if op not in OPS:
        raise StepConfigError("run-if has an unknown comparison.")
    if op in ("matched", "not_matched"):
        if "matched" not in outputs[ref]:
            raise StepConfigError(f"`{ref}` is not a filter, so it has no match result.")
        return {"step": ref, "op": op}
    fld = str(raw.get("field") or "").strip()
    if fld not in outputs[ref]:
        raise StepConfigError(f"`{ref}` has no output `{fld or '(none)'}`.")
    out: dict[str, Any] = {"step": ref, "field": fld, "op": op}
    if op in LIST_OPS:
        val = raw.get("value")
        items = val if isinstance(val, list) else str(val or "").split(",")
        items = [str(v).strip()[:CONDITION_VALUE_LIMIT] for v in items if str(v).strip()]
        if not items:
            raise StepConfigError("run-if needs at least one value.")
        out["value"] = items[:50]
    elif op in VALUE_OPS:
        out["value"] = str(raw.get("value") or "").strip()[:CONDITION_VALUE_LIMIT]
    return out


def validate_steps(
    steps: Any, *, discord_ids: set[int], model_ids: set[str] | None,
    http_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Normalise a task's step list. `model_ids` is None when the provider's
    model list is unavailable; explicit models are then only checked at run
    time."""
    if not isinstance(steps, list) or not steps:
        raise StepConfigError("A task needs at least one step.")
    if len(steps) > MAX_STEPS:
        raise StepConfigError(f"A task can have at most {MAX_STEPS} steps.")
    vctx = ValidateContext(discord_ids=discord_ids, model_ids=model_ids, http_ids=set(http_ids or ()))
    out: list[dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        try:
            out.append(_validate_step(step, vctx))
        except StepConfigError as e:
            raise StepConfigError(f"Step {i}: {e}") from e
    return out


def _validate_step(step: Any, vctx: ValidateContext) -> dict[str, Any]:
    if not isinstance(step, dict) or step.get("type") not in REGISTRY:
        raise StepConfigError("unknown step type.")
    d = REGISTRY[step["type"]]
    cfg = step.get("config") or {}
    if not isinstance(cfg, dict):
        raise StepConfigError("invalid config.")
    norm: dict[str, Any] = {"type": d.type, "config": d.validate(cfg, vctx)}

    name = str(step.get("name") or "").strip().lower()
    if name:
        if not NAME_RE.match(name):
            raise StepConfigError(
                "a step name must start with a letter and use only a-z, 0-9 and _ "
                "(at most 32 characters)."
            )
        if name in RESERVED_NAMES or name in vctx.outputs:
            raise StepConfigError(f"the name `{name}` is already used.")
        norm["name"] = name

    when = _validate_when(step.get("when"), vctx.outputs)
    if when:
        norm["when"] = when
    if step.get("on_error") == "continue":
        norm["on_error"] = "continue"
    if d.group == "filter":
        if step.get("negate") is True:
            norm["negate"] = True
        if step.get("on_no_match") == "continue":
            norm["on_no_match"] = "continue"

    if name:
        vctx.outputs[name] = step_outputs(norm)
    return norm


def step_refs(steps: list[dict[str, Any]]) -> set[int]:
    """Integration ids used by these steps."""
    ids: set[int] = set()
    for s in steps:
        d = REGISTRY.get(s.get("type"))
        if d is not None:
            ids |= d.refs(s.get("config") or {})
    return ids


def llm_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in steps if (d := REGISTRY.get(s.get("type"))) is not None and d.uses_llm]


def step_types_meta() -> list[dict[str, Any]]:
    return [
        {"type": d.type, "label": d.label, "group": d.group, "group_label": GROUP_LABELS[d.group],
         "uses_llm": d.uses_llm}
        for d in REGISTRY.values()
    ]


# --- conditions --------------------------------------------------------------


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ", ".join(_text(x) for x in v)
    return str(v).strip().lower()


def condition_holds(when: dict[str, Any], state: RunState) -> bool:
    out = state.vars.get(when["step"])
    op = when["op"]
    if op == "matched":
        return bool(out) and out.get("matched") is True
    if op == "not_matched":
        return bool(out) and out.get("matched") is False
    val = _text((out or {}).get(when.get("field", "")))
    if op == "is_set":
        return val != ""
    if op == "is_empty":
        return val == ""
    if op in LIST_OPS:
        hit = val in {_text(x) for x in when["value"]}
        return hit if op == "in" else not hit
    want = _text(when.get("value"))
    if op == "equals":
        return val == want
    if op == "not_equals":
        return val != want
    return want in val  # contains


def describe_condition(when: dict[str, Any]) -> str:
    op = when["op"].replace("_", " ")
    if op in ("matched", "not matched"):
        return f"{when['step']} {op}"
    target = f"{when['step']}.{when.get('field')}"
    val = when.get("value")
    if isinstance(val, list):
        val = ", ".join(val)
    return f"{target} {op}" + (f" {val}" if val is not None else "")


# --- execution ---------------------------------------------------------------


@dataclass
class RunResult:
    status: str  # completed | partial | stopped | error
    log: list[dict[str, Any]]
    # (step type, attempt) for every model attempt, including failed steps.
    usage: list[tuple[str, llm.UsageAttempt]] = field(default_factory=list)
    vars: dict[str, dict[str, Any]] = field(default_factory=dict)


def run_task(steps: list[dict[str, Any]], mail: ParsedEmail, ctx: RunContext) -> RunResult:
    state = RunState()
    status = _run_steps(steps, mail, ctx, state, log := [])
    return RunResult(status, log, usage=state.usage, vars=state.vars)


def _run_steps(
    steps: list[dict[str, Any]], mail: ParsedEmail, ctx: RunContext, state: RunState,
    log: list[dict[str, Any]],
) -> str:
    had_error = False
    for i, step in enumerate(steps, 1):
        kind = step.get("type")
        d = REGISTRY.get(kind)
        entry: dict[str, Any] = {"step": i, "type": kind, "label": d.label if d else kind}
        if step.get("name"):
            entry["name"] = step["name"]
        log.append(entry)

        when = step.get("when")
        if when and not condition_holds(when, state):
            entry.update(outcome="skip", detail=f"condition not met: {describe_condition(when)}")
            continue

        try:
            if d is None:
                raise StepConfigError(f"Unknown step type {kind}.")
            res = d.run(step.get("config") or {}, mail, ctx, state, entry)
        except _DOMAIN_ERRORS as e:
            entry.update(outcome="error", detail=str(e))
        except Exception as e:  # keep the poller alive on unexpected failures
            entry.update(outcome="error", detail=f"internal error: {type(e).__name__}: {e}")
        else:
            out = dict(res.vars or {})
            if d.group == "filter":
                matched = bool(res.matched) != bool(step.get("negate"))
                out["matched"] = matched
                detail = res.detail
                if step.get("negate"):
                    detail = f"inverted: {detail}" if detail else "inverted"
                if matched:
                    entry.update(outcome="pass", detail=detail)
                elif step.get("on_no_match") == "continue":
                    entry.update(outcome="no-match", detail=detail)
                else:
                    entry.update(outcome="stop", detail=detail)
                    _save_vars(step, state, out)
                    return "stopped"
            else:
                entry.update(outcome=res.outcome, detail=res.detail)
            _save_vars(step, state, out)
            continue

        # The step errored.
        if step.get("on_error") != "continue":
            return "error"
        had_error = True
    return "partial" if had_error else "completed"


def _save_vars(step: dict[str, Any], state: RunState, out: dict[str, Any]) -> None:
    if step.get("name"):
        state.vars[step["name"]] = out
