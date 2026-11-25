"""Built-in (non-LLM) filter, modelled on Gmail's filter fields.

Fields (all optional, all case-insensitive, combined with AND):
- from / to / subject: substring match; several alternatives may be given
  separated by `,` or ` OR ` and any one matching is enough.
- has_words: every term must appear in subject or body. Use "quotes" for
  phrases.
- not_words: no term may appear in subject or body.
- has_attachment: true/false to require presence/absence; null ignores.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from .gmail import ParsedEmail

FIELDS = ("from", "to", "subject", "has_words", "not_words", "has_attachment")


def _alternatives(value: str) -> list[str]:
    parts = re.split(r",|\s+OR\s+", value)
    return [p.strip().lower() for p in parts if p.strip()]


def _terms(value: str) -> list[str]:
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = value.split()
    return [p.lower() for p in parts if p.strip()]


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("from", "to", "subject", "has_words", "not_words"):
        v = cfg.get(key)
        out[key] = str(v).strip()[:1000] if v else ""
    ha = cfg.get("has_attachment")
    out["has_attachment"] = ha if isinstance(ha, bool) else None
    return out


def is_empty(cfg: dict[str, Any]) -> bool:
    return not any(cfg.get(k) for k in ("from", "to", "subject", "has_words", "not_words")) and (
        cfg.get("has_attachment") is None
    )


def matches(cfg: dict[str, Any], mail: ParsedEmail) -> tuple[bool, str]:
    """Returns (matched, reason)."""
    checks = (("from", mail.sender), ("to", f"{mail.to} {mail.cc}"), ("subject", mail.subject))
    for key, haystack in checks:
        if cfg.get(key):
            alts = _alternatives(cfg[key])
            if not any(a in haystack.lower() for a in alts):
                return False, f"`{key}` did not match"

    text = f"{mail.subject}\n{mail.body}".lower()
    if cfg.get("has_words"):
        missing = [t for t in _terms(cfg["has_words"]) if t not in text]
        if missing:
            return False, f"missing words: {', '.join(missing)}"
    if cfg.get("not_words"):
        found = [t for t in _terms(cfg["not_words"]) if t in text]
        if found:
            return False, f"contains excluded words: {', '.join(found)}"

    if cfg.get("has_attachment") is True and not mail.has_attachment:
        return False, "no attachment"
    if cfg.get("has_attachment") is False and mail.has_attachment:
        return False, "has an attachment"
    return True, "all criteria matched"
