"""Display masking for the user's own account identifiers.

Connected Gmail addresses and API keys are shown masked everywhere in the UI.
Only the Integrations page also receives the revealable form.
"""

from __future__ import annotations

import re

ANTHROPIC_KEY_PREFIX = "sk-ant-"


def mask_email(addr: str | None) -> str:
    """`johndoe+tag@gmail.com` -> `j*****e+tag@gmail.com`; domain and `+tag` kept."""
    if not addr:
        return ""
    local, at, domain = addr.rpartition("@")
    if not at:
        local, domain = addr, ""
    base, plus, tag = local.partition("+")
    if len(base) <= 2:
        masked = "*" * len(base)
    else:
        masked = base[0] + "*" * (len(base) - 2) + base[-1]
    return f"{masked}{plus}{tag}{at}{domain}"


def mask_name(name: str | None) -> str:
    """`John Doe` -> `J*** D**`: first character of each word kept, spacing kept."""
    return re.sub(r"\S+", lambda m: m.group()[0] + "*" * (len(m.group()) - 1), name or "")


def key_prefix(hint: str | None) -> str:
    """The fixed, non-identifying start of a stored Anthropic key hint."""
    return ANTHROPIC_KEY_PREFIX if (hint or "").startswith(ANTHROPIC_KEY_PREFIX) else ""
