"""Shared types for task steps.

Each step type is a `StepDef` registered in `steps/__init__.py`. The engine in
`services/pipeline.py` handles what every step shares (names, run-if
conditions, error handling, filter inversion); a step module only validates
its own config and does its own work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .. import llm, prompts
from ..gmail import ParsedEmail

LOG_TEXT_LIMIT = 4000


class StepConfigError(ValueError):
    """A step's saved config is invalid. Shown to the user at save time."""


class StepError(Exception):
    """User-presentable failure while running a step."""


@dataclass
class RunContext:
    api_key: str | None
    default_model: str | None
    # id -> (display name, webhook url)
    discord: dict[int, tuple[str, str]] = field(default_factory=dict)
    # The user's IANA time zone, if known.
    timezone: str | None = None
    # Fixed clock for tests; None means the real time.
    now: datetime | None = None


@dataclass
class ValidateContext:
    discord_ids: set[int]
    # None when the provider's model list is unavailable.
    model_ids: set[str] | None
    # Named earlier steps -> the fields they output.
    outputs: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class RunState:
    # step name -> output fields, for conditions and templates.
    vars: dict[str, dict[str, Any]] = field(default_factory=dict)
    # (step type, attempt) for every model attempt, including failed steps.
    usage: list[tuple[str, llm.UsageAttempt]] = field(default_factory=list)


@dataclass
class Result:
    # Filters set `matched`; the engine turns it into pass/stop/no-match.
    # Other steps set `outcome` ("pass" or "sent").
    outcome: str = "pass"
    detail: str = ""
    matched: bool | None = None
    vars: dict[str, Any] | None = None


Validate = Callable[[dict[str, Any], ValidateContext], dict[str, Any]]
Run = Callable[[dict[str, Any], ParsedEmail, RunContext, RunState, dict[str, Any]], Result]


def _no_outputs(cfg: dict[str, Any]) -> list[str]:
    return []


def _no_refs(cfg: dict[str, Any]) -> set[int]:
    return set()


@dataclass(frozen=True)
class StepDef:
    type: str
    label: str
    group: str  # filter | agent | action
    validate: Validate
    run: Run
    uses_llm: bool = False
    # Output fields a named step exposes to later steps.
    outputs: Callable[[dict[str, Any]], list[str]] = _no_outputs
    # Integration ids the config refers to (blocks deleting them).
    refs: Callable[[dict[str, Any]], set[int]] = _no_refs


def clip(text: str, limit: int = LOG_TEXT_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def validate_model(cfg: dict[str, Any], vctx: ValidateContext) -> str | None:
    model = str(cfg.get("model") or "").strip() or None
    if model and vctx.model_ids is not None and model not in vctx.model_ids:
        raise StepConfigError(f"model `{model}` is not offered by the provider.")
    return model


def validate_instructions(cfg: dict[str, Any], limit: int = 8000, *, required: bool = True) -> str:
    text = str(cfg.get("instructions") or "").strip()
    if required and not text:
        raise StepConfigError("instructions are required.")
    if len(text) > limit:
        raise StepConfigError("instructions are too long.")
    return text


def validate_discord(cfg: dict[str, Any], vctx: ValidateContext) -> int:
    try:
        did = int(cfg.get("discord_integration_id"))
    except (TypeError, ValueError):
        did = None
    if did not in vctx.discord_ids:
        raise StepConfigError("pick a Discord webhook.")
    return did


def discord_refs(cfg: dict[str, Any]) -> set[int]:
    did = cfg.get("discord_integration_id")
    return {did} if isinstance(did, int) else set()


def call_llm(
    ctx: RunContext, cfg: dict[str, Any], prompt: prompts.Prompt,
    entry: dict[str, Any], state: RunState, **kwargs: Any,
) -> llm.LLMResult:
    if not ctx.api_key:
        raise llm.LLMError("No Anthropic integration is set up.")
    model = cfg.get("model") or ctx.default_model
    if not model:
        raise llm.LLMError("No model chosen for this step and no default model in Settings.")
    res = llm.complete(ctx.api_key, model, prompt.system, prompt.user, **kwargs)
    state.usage.extend((entry["type"], a) for a in res.usage)
    if res.usage:
        costs = [a.cost_nanos() for a in res.usage]
        entry["usage"] = {
            "input_tokens": sum(a.tokens.prompt for a in res.usage),
            "output_tokens": sum(a.tokens.output for a in res.usage),
            "cost_nanousd": None if None in costs else sum(costs),
        }
    return res
