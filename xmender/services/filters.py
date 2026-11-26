"""Built-in (non-LLM) filter, modelled on Gmail's filter fields.

Fields (all optional, all case-insensitive, combined with AND):
- from / to / subject: substring match; several alternatives may be given
  separated by `,` or ` OR ` and any one matching is enough.
- has_words: every term must appear in subject or body. Use "quotes" for
  phrases.
- not_words: no term may appear in subject or body.
- regex: when true, each text field above is one regular expression instead
  (searched, not anchored). Patterns run with a timeout so a slow pattern can
  never hang the poller.
- has_attachment: true/false to require presence/absence; null ignores.
- attachment_ext / attachment_name / attachment_type / attachment_min_kb /
  attachment_max_kb: at least one attachment must satisfy all of those set.
  Setting any of them implies an attachment is required.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from typing import Any

import regex

from .gmail import Attachment, ParsedEmail

TEXT_FIELDS = ("from", "to", "subject", "has_words", "not_words")
ATTACHMENT_TEXT = ("attachment_ext", "attachment_name", "attachment_type")
ATTACHMENT_SIZE = ("attachment_min_kb", "attachment_max_kb")
FIELDS = TEXT_FIELDS + ("regex", "has_attachment") + ATTACHMENT_TEXT + ATTACHMENT_SIZE

REGEX_TIMEOUT = 0.25  # seconds per search
REGEX_TEXT_LIMIT = 200_000  # characters of subject+body searched in regex mode
MAX_KB = 10_000_000


class FilterError(Exception):
    """User-presentable failure while matching (a regex timeout)."""


def _alternatives(value: str) -> list[str]:
    parts = re.split(r",|\s+OR\s+", value)
    return [p.strip().lower() for p in parts if p.strip()]


def _list(value: str) -> list[str]:
    return [p.strip().lower() for p in value.split(",") if p.strip()]


def _terms(value: str) -> list[str]:
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = value.split()
    return [p.lower() for p in parts if p.strip()]


def compile_pattern(pattern: str) -> regex.Pattern:
    """Raises ValueError with a readable message."""
    try:
        return regex.compile(pattern, regex.IGNORECASE)
    except regex.error as e:
        raise ValueError(f"invalid regular expression `{pattern}`: {e}") from e


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalise a config. Raises ValueError for an invalid regex or size."""
    out: dict[str, Any] = {}
    for key in TEXT_FIELDS + ATTACHMENT_TEXT:
        v = cfg.get(key)
        out[key] = str(v).strip()[:1000] if v else ""
    out["regex"] = cfg.get("regex") is True
    ha = cfg.get("has_attachment")
    out["has_attachment"] = ha if isinstance(ha, bool) else None
    for key in ATTACHMENT_SIZE:
        v = cfg.get(key)
        if v in (None, ""):
            out[key] = None
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("attachment sizes must be whole numbers of KB.") from None
        if not 0 <= n <= MAX_KB:
            raise ValueError("attachment size is out of range.")
        out[key] = n
    if out["regex"]:
        for key in TEXT_FIELDS:
            if out[key]:
                compile_pattern(out[key])
    if (out["attachment_min_kb"] is not None and out["attachment_max_kb"] is not None
            and out["attachment_min_kb"] > out["attachment_max_kb"]):
        raise ValueError("the minimum attachment size is larger than the maximum.")
    if out["has_attachment"] is False and _wants_attachment_detail(out):
        raise ValueError("attachment details are set, but the filter requires no attachment.")
    return out


def _wants_attachment_detail(cfg: dict[str, Any]) -> bool:
    return any(cfg.get(k) for k in ATTACHMENT_TEXT) or any(
        cfg.get(k) is not None for k in ATTACHMENT_SIZE
    )


def is_empty(cfg: dict[str, Any]) -> bool:
    return (
        not any(cfg.get(k) for k in TEXT_FIELDS)
        and cfg.get("has_attachment") is None
        and not _wants_attachment_detail(cfg)
    )


def _search(pattern: str, text: str) -> bool:
    try:
        return compile_pattern(pattern).search(text[:REGEX_TEXT_LIMIT], timeout=REGEX_TIMEOUT) is not None
    except TimeoutError as e:
        raise FilterError(f"the regular expression `{pattern}` took too long and was stopped.") from e


def _attachment_ok(cfg: dict[str, Any], att: Attachment) -> bool:
    if cfg.get("attachment_ext"):
        exts = [e.lstrip(".") for e in _list(cfg["attachment_ext"])]
        if att.extension not in exts:
            return False
    if cfg.get("attachment_name"):
        if not any(fnmatch.fnmatch(att.name.lower(), g) for g in _list(cfg["attachment_name"])):
            return False
    if cfg.get("attachment_type"):
        if not any(att.content_type.lower().startswith(t) for t in _list(cfg["attachment_type"])):
            return False
    lo, hi = cfg.get("attachment_min_kb"), cfg.get("attachment_max_kb")
    if lo is not None and att.size < lo * 1024:
        return False
    if hi is not None and att.size > hi * 1024:
        return False
    return True


def matches(cfg: dict[str, Any], mail: ParsedEmail) -> tuple[bool, str]:
    """Returns (matched, reason). Raises FilterError if a regex times out."""
    use_re = cfg.get("regex") is True
    checks = (("from", mail.sender), ("to", f"{mail.to} {mail.cc}"), ("subject", mail.subject))
    for key, haystack in checks:
        if cfg.get(key):
            if use_re:
                ok = _search(cfg[key], haystack)
            else:
                ok = any(a in haystack.lower() for a in _alternatives(cfg[key]))
            if not ok:
                return False, f"`{key}` did not match"

    text = f"{mail.subject}\n{mail.body}"
    if cfg.get("has_words"):
        if use_re:
            if not _search(cfg["has_words"], text):
                return False, "`has_words` pattern not found"
        else:
            missing = [t for t in _terms(cfg["has_words"]) if t not in text.lower()]
            if missing:
                return False, f"missing words: {', '.join(missing)}"
    if cfg.get("not_words"):
        if use_re:
            if _search(cfg["not_words"], text):
                return False, "`not_words` pattern found"
        else:
            found = [t for t in _terms(cfg["not_words"]) if t in text.lower()]
            if found:
                return False, f"contains excluded words: {', '.join(found)}"

    if cfg.get("has_attachment") is True and not mail.has_attachment:
        return False, "no attachment"
    if cfg.get("has_attachment") is False and mail.has_attachment:
        return False, "has an attachment"
    if _wants_attachment_detail(cfg):
        hits = [a for a in mail.attachments if _attachment_ok(cfg, a)]
        if not hits:
            return False, "no attachment matches the attachment details"
        return True, f"all criteria matched (attachment: {hits[0].name})"
    return True, "all criteria matched"
