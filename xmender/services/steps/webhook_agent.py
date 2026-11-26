"""Webhook (Agent): the model writes a Discord notification."""

from __future__ import annotations

from typing import Any

from .. import discord, llm, prompts
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepDef, ValidateContext, add_warning, call_llm, clip,
    discord_refs, validate_attachments, validate_discord, validate_instructions, validate_model,
)

WEBHOOK_TEXT_TARGET = 3500


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    return validate_attachments(cfg, {
        "instructions": validate_instructions(cfg),
        "model": validate_model(cfg, vctx),
        "discord_integration_id": validate_discord(cfg, vctx),
    })


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    hook = ctx.discord.get(cfg.get("discord_integration_id"))
    if hook is None:
        raise discord.DiscordError("The Discord webhook for this step was removed.")
    prompt = prompts.webhook_agent_prompt(cfg["instructions"], mail, WEBHOOK_TEXT_TARGET)
    res = call_llm(ctx, cfg, prompt, entry, state, mail=mail)
    entry.update(model=res.model, response=clip(res.text))
    if res.stop_reason == "refusal":
        raise llm.LLMError("Model declined to write the notification.")
    if res.stop_reason == "max_tokens":
        add_warning(entry, "response hit max_tokens and was cut")
    name, url = hook
    discord.send_embed(
        url,
        description=res.text,
        footer=f"Subject: {mail.subject}" if mail.subject else None,
        thread_name=mail.subject or None,
    )
    return Result(outcome="sent", detail=f"posted to {name}")


STEP = StepDef(
    type="webhook_agent", label="Webhook (Agent)", group="action",
    validate=_validate, run=_run, uses_llm=True, refs=discord_refs,
)
