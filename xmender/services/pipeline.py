"""Task steps: validation and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import discord, filters, llm, prompts
from .gmail import ParsedEmail

STEP_TYPES = {
    "filter_builtin": "Filter (Built-in)",
    "filter_agent": "Filter (Agent)",
    "webhook_agent": "Webhook (Agent)",
}
INSTRUCTIONS_LIMIT = 8000
WEBHOOK_TEXT_TARGET = 3500
LOG_TEXT_LIMIT = 4000


class StepConfigError(ValueError):
    pass


def validate_steps(
    steps: Any, *, discord_ids: set[int], model_ids: set[str] | None
) -> list[dict[str, Any]]:
    """Normalise a task's step list. `model_ids` is None when the provider's
    model list is unavailable; explicit models are then only checked at run
    time."""
    if not isinstance(steps, list) or not steps:
        raise StepConfigError("A task needs at least one step.")
    if len(steps) > 50:
        raise StepConfigError("A task can have at most 50 steps.")
    out: list[dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("type") not in STEP_TYPES:
            raise StepConfigError(f"Step {i}: unknown step type.")
        cfg = step.get("config") or {}
        if not isinstance(cfg, dict):
            raise StepConfigError(f"Step {i}: invalid config.")
        kind = step["type"]
        if kind == "filter_builtin":
            norm = filters.normalize_config(cfg)
            if filters.is_empty(norm):
                raise StepConfigError(f"Step {i}: set at least one filter criterion.")
        else:
            instructions = str(cfg.get("instructions") or "").strip()
            if not instructions:
                raise StepConfigError(f"Step {i}: instructions are required.")
            if len(instructions) > INSTRUCTIONS_LIMIT:
                raise StepConfigError(f"Step {i}: instructions are too long.")
            model = str(cfg.get("model") or "").strip() or None
            if model and model_ids is not None and model not in model_ids:
                raise StepConfigError(f"Step {i}: model `{model}` is not offered by the provider.")
            norm = {"instructions": instructions, "model": model}
            if kind == "webhook_agent":
                try:
                    did = int(cfg.get("discord_integration_id"))
                except (TypeError, ValueError):
                    did = None
                if did not in discord_ids:
                    raise StepConfigError(f"Step {i}: pick a Discord webhook.")
                norm["discord_integration_id"] = did
        out.append({"type": kind, "config": norm})
    return out


@dataclass
class RunContext:
    api_key: str | None
    default_model: str | None
    # id -> (display name, webhook url)
    discord: dict[int, tuple[str, str]] = field(default_factory=dict)


@dataclass
class RunResult:
    status: str  # completed | stopped | error
    log: list[dict[str, Any]]


def _clip(text: str) -> str:
    return text if len(text) <= LOG_TEXT_LIMIT else text[:LOG_TEXT_LIMIT] + "…"


def _llm(ctx: RunContext, cfg: dict[str, Any], prompt: prompts.Prompt) -> llm.LLMResult:
    if not ctx.api_key:
        raise llm.LLMError("No Anthropic integration is set up.")
    model = cfg.get("model") or ctx.default_model
    if not model:
        raise llm.LLMError("No model chosen for this step and no default model in Settings.")
    return llm.complete(ctx.api_key, model, prompt.system, prompt.user)


def run_task(steps: list[dict[str, Any]], mail: ParsedEmail, ctx: RunContext) -> RunResult:
    log: list[dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        kind, cfg = step["type"], step.get("config") or {}
        entry: dict[str, Any] = {"step": i, "type": kind, "label": STEP_TYPES.get(kind, kind)}
        log.append(entry)
        try:
            if kind == "filter_builtin":
                ok, reason = filters.matches(cfg, mail)
                entry.update(outcome="pass" if ok else "stop", detail=reason)
                if not ok:
                    return RunResult("stopped", log)

            elif kind == "filter_agent":
                res = _llm(ctx, cfg, prompts.filter_agent_prompt(cfg["instructions"], mail))
                entry.update(model=res.model, response=_clip(res.text))
                if res.stop_reason == "refusal":
                    entry.update(outcome="stop", detail="model declined to answer")
                    return RunResult("stopped", log)
                ok = prompts.is_filter_match(res.text)
                entry.update(
                    outcome="pass" if ok else "stop",
                    detail="FILTER MATCH" if ok else "no match",
                )
                if not ok:
                    return RunResult("stopped", log)

            elif kind == "webhook_agent":
                hook = ctx.discord.get(cfg.get("discord_integration_id"))
                if hook is None:
                    raise discord.DiscordError("The Discord webhook for this step was removed.")
                res = _llm(
                    ctx,
                    cfg,
                    prompts.webhook_agent_prompt(cfg["instructions"], mail, WEBHOOK_TEXT_TARGET),
                )
                entry.update(model=res.model, response=_clip(res.text))
                if res.stop_reason == "refusal":
                    raise llm.LLMError("Model declined to write the notification.")
                if res.stop_reason == "max_tokens":
                    entry["warning"] = "response hit max_tokens and was cut"
                name, url = hook
                discord.send_embed(
                    url,
                    username=name,
                    description=res.text,
                    footer=f"Subject: {mail.subject}" if mail.subject else None,
                    thread_name=mail.subject or None,
                )
                entry.update(outcome="sent", detail=f"posted to {name}")
            else:
                raise StepConfigError(f"Unknown step type {kind}.")
        except (llm.LLMError, discord.DiscordError, StepConfigError) as e:
            entry.update(outcome="error", detail=str(e))
            return RunResult("error", log)
        except Exception as e:  # keep the poller alive on unexpected failures
            entry.update(outcome="error", detail=f"internal error: {type(e).__name__}: {e}")
            return RunResult("error", log)
    return RunResult("completed", log)
