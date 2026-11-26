"""Template post: a Discord embed filled from a template, no LLM."""

from __future__ import annotations

from typing import Any

from .. import discord, template
from ..gmail import ParsedEmail
from .base import (
    Result, RunContext, RunState, StepConfigError, StepDef, ValidateContext, clip, discord_refs,
    validate_discord,
)

DEFAULT_BODY = "**{{email.subject}}**\nFrom: {{email.from}}\n\n{{email.snippet}}"


def validate_template(cfg: dict[str, Any], key: str, vctx: ValidateContext, *,
                      required: bool = False, limit: int = template.TEMPLATE_LIMIT) -> str:
    text = str(cfg.get(key) or "").strip()
    if required and not text:
        raise StepConfigError(f"the {key} template is empty.")
    if len(text) > limit:
        raise StepConfigError(f"the {key} template is too long (at most {limit} characters).")
    try:
        template.check(text, vctx.outputs)
    except template.TemplateError as e:
        raise StepConfigError(f"{key}: {e}") from e
    return text


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    return {
        "discord_integration_id": validate_discord(cfg, vctx),
        "title": validate_template(cfg, "title", vctx, limit=500),
        "body": validate_template(cfg, "body", vctx, required=True),
        "footer": validate_template(cfg, "footer", vctx, limit=500),
    }


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    hook = ctx.discord.get(cfg.get("discord_integration_id"))
    if hook is None:
        raise discord.DiscordError("The Discord webhook for this step was removed.")
    scope = template.scope_for(mail, state.vars)
    warnings: list[str] = []
    parts = {}
    for key in ("title", "body", "footer"):
        parts[key], w = template.render(cfg.get(key) or "", scope)
        warnings += w
    if warnings:
        entry["warning"] = "; ".join(dict.fromkeys(warnings))
    entry["response"] = clip(parts["body"])
    name, url = hook
    discord.send_embed(
        url,
        title=parts["title"] or None,
        description=parts["body"],
        footer=parts["footer"] or None,
        thread_name=mail.subject or None,
    )
    return Result(outcome="sent", detail=f"posted to {name}")


STEP = StepDef(
    type="template_post", label="Template post (Discord)", group="action",
    validate=_validate, run=_run, refs=discord_refs,
)
