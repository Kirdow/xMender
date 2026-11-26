"""Tiny text templates: `{{ email.subject }}`, `{{ step.field | clip:200 }}`.

No logic, loops or code. A placeholder is a dotted path followed by optional
modifiers:
- `clip:N` cuts to N characters (adds "…").
- `default:text` is used when the value is empty.
- `oneline` collapses whitespace to single spaces.
- `upper` / `lower`.
Values are inserted as plain text. Unknown paths render empty and are
reported as warnings; validation at save time catches them early.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .gmail import ParsedEmail

TEMPLATE_LIMIT = 4000
_PLACEHOLDER = re.compile(r"\{\{\s*(.*?)\s*\}\}", re.DOTALL)
_PATH = re.compile(r"^([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)$")
MODIFIERS = {"clip", "default", "oneline", "upper", "lower"}

EMAIL_FIELDS = (
    "from", "from_name", "from_addr", "to", "cc", "subject", "date", "snippet", "body",
    "attachments", "attachment_count",
)


class TemplateError(ValueError):
    """Invalid template syntax. Message is user-presentable."""


@dataclass(frozen=True)
class Placeholder:
    raw: str
    ns: str
    field: str
    mods: tuple[tuple[str, str | None], ...]


def parse(template: str) -> list[Placeholder]:
    if len(template) > TEMPLATE_LIMIT:
        raise TemplateError(f"a template can be at most {TEMPLATE_LIMIT} characters.")
    out: list[Placeholder] = []
    for m in _PLACEHOLDER.finditer(template):
        parts = [p.strip() for p in m.group(1).split("|")]
        path = _PATH.match(parts[0].lower())
        if not path:
            raise TemplateError(f"`{m.group(0)}` is not a valid placeholder; use {{{{step.field}}}}.")
        mods: list[tuple[str, str | None]] = []
        for raw_mod in parts[1:]:
            name, colon, arg = raw_mod.partition(":")
            name = name.strip().lower()
            if name not in MODIFIERS:
                raise TemplateError(f"unknown modifier `{name}` in `{m.group(0)}`.")
            if name == "clip":
                if not arg.strip().isdigit() or int(arg) < 1:
                    raise TemplateError("`clip` needs a positive number, as in clip:200.")
            mods.append((name, arg if colon else None))
        out.append(Placeholder(m.group(0), path.group(1), path.group(2), tuple(mods)))
    return out


def check(template: str, outputs: dict[str, set[str]]) -> None:
    """Validate syntax and that every path exists. `outputs` maps earlier
    named steps to their fields; `email` is always available."""
    for p in parse(template):
        if p.ns == "email":
            if p.field not in EMAIL_FIELDS:
                raise TemplateError(f"`{p.raw}`: emails have no field `{p.field}`.")
        elif p.ns not in outputs:
            raise TemplateError(f"`{p.raw}` refers to `{p.ns}`, which is not a named earlier step.")
        elif p.field not in outputs[p.ns]:
            raise TemplateError(f"`{p.raw}`: step `{p.ns}` has no output `{p.field}`.")


def email_vars(mail: ParsedEmail) -> dict[str, Any]:
    return {
        "from": mail.sender,
        "from_name": mail.from_name,
        "from_addr": mail.from_addr,
        "to": mail.to,
        "cc": mail.cc,
        "subject": mail.subject,
        "date": mail.date.isoformat() if mail.date else "",
        "snippet": mail.snippet(),
        "body": mail.body,
        "attachments": ", ".join(a.name for a in mail.attachments),
        "attachment_count": len(mail.attachments),
    }


def to_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return ", ".join(to_text(x) for x in v)
    return str(v)


def _apply(value: str, mods: tuple[tuple[str, str | None], ...]) -> str:
    for name, arg in mods:
        if name == "clip":
            n = int(arg or 0)
            value = value if len(value) <= n else value[: max(n - 1, 0)] + "…"
        elif name == "default":
            value = value if value.strip() else (arg or "")
        elif name == "oneline":
            value = re.sub(r"\s+", " ", value).strip()
        elif name == "upper":
            value = value.upper()
        elif name == "lower":
            value = value.lower()
    return value


def render(template: str, scope: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Fill placeholders from `scope` ({"email": {...}, step: {...}}).
    Returns the text and warnings for paths with no value."""
    warnings: list[str] = []
    placeholders = {p.raw: p for p in parse(template)}

    def sub(m: re.Match[str]) -> str:
        p = placeholders[m.group(0)]
        ns = scope.get(p.ns)
        if ns is None or p.field not in ns:
            warnings.append(f"{p.ns}.{p.field} had no value")
            value = ""
        else:
            value = to_text(ns[p.field])
        return _apply(value, p.mods)

    return _PLACEHOLDER.sub(sub, template), warnings


def scope_for(mail: ParsedEmail, step_vars: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {**step_vars, "email": email_vars(mail)}
