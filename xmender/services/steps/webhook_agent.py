"""Webhook (Agent): the model writes a Discord notification.

The embed title is the fixed default, written by the model (`title_mode:
generate`, first reply line `Title: ...`), or a template (`title_mode:
template`).
"""

from __future__ import annotations

import re
from typing import Any

from .. import discord, llm, prompts, template
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext, add_warning,
    call_llm, clip, discord_refs, validate_attachments, validate_discord, validate_instructions,
    validate_model,
)
from .template_post import validate_template

WEBHOOK_TEXT_TARGET = 3500
TITLE_MODES = ("generate", "template")
TITLE_TARGET = 80
# "Title: x", tolerating markdown the model may wrap around it ("**Title:** x", "# Title: x").
_TITLE_RE = re.compile(r"^[\s*_#]*title[\s*_]*:[\s*_]*(.*?)[\s*_]*$", re.IGNORECASE)


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    out = validate_attachments(cfg, {
        "instructions": validate_instructions(cfg),
        "model": validate_model(cfg, vctx),
        "discord_integration_id": validate_discord(cfg, vctx),
    })
    mode = cfg.get("title_mode")
    if mode == "generate":
        out["title_mode"] = mode
    elif mode == "template":
        out["title_mode"] = mode
        out["title"] = validate_template(cfg, "title", vctx, limit=500)
        if not out["title"]:
            raise StepConfigError("the title template is empty.")
    elif mode not in (None, "", "default"):
        raise StepConfigError("unknown title mode.")
    return out


def split_title(text: str) -> tuple[str | None, str]:
    """(title, body) from a reply whose first non-empty line is `Title: ...`."""
    lines = text.strip().splitlines()
    if not lines:
        return None, ""
    m = _TITLE_RE.match(lines[0])
    if not m:
        return None, text
    title = m.group(1).strip()
    return title or None, "\n".join(lines[1:]).strip()


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    hook = ctx.discord.get(cfg.get("discord_integration_id"))
    if hook is None:
        raise discord.DiscordError("The Discord webhook for this step was removed.")
    mode = cfg.get("title_mode")
    prompt = prompts.webhook_agent_prompt(
        cfg["instructions"], mail, WEBHOOK_TEXT_TARGET,
        title_chars=TITLE_TARGET if mode == "generate" else None,
    )
    res = call_llm(ctx, cfg, prompt, entry, state, mail=mail)
    entry.update(model=res.model, response=clip(res.text))
    if res.stop_reason == "refusal":
        raise llm.LLMError("Model declined to write the notification.")
    if res.stop_reason == "max_tokens":
        add_warning(entry, "response hit max_tokens and was cut")
    title, body = None, res.text
    if mode == "generate":
        title, body = split_title(res.text)
        if title is None:
            add_warning(entry, "model wrote no title line; used the default title")
    elif mode == "template":
        title, warnings = template.render(cfg.get("title") or "", template.scope_for(mail, state.vars))
        for w in dict.fromkeys(warnings):
            add_warning(entry, w)
        title = title.strip() or None
    name, url = hook
    discord.send_embed(
        url,
        title=title,
        description=body,
        footer=f"Subject: {mail.subject}" if mail.subject else None,
        thread_name=mail.subject or None,
    )
    return Result(outcome="sent", detail=f"posted to {name}")


STEP = StepDef(
    type="webhook_agent", label="Webhook (Agent)", group="action",
    validate=_validate, run=_run, uses_llm=True, refs=discord_refs,
)
