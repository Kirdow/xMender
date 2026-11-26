"""Header-based signals about an email: bulk/newsletter and phishing hints.

Everything here is deterministic and uses only the parsed message, so it is
free to run before any LLM step.
"""

from __future__ import annotations

import re

from .gmail import ParsedEmail

# --- bulk / newsletter -------------------------------------------------------

BULK_KINDS = {
    "newsletter": "Newsletter or mailing list (List-Unsubscribe / List-Id)",
    "bulk": "Bulk or automated (Precedence, Auto-Submitted, Feedback-ID)",
    "noreply": "Sent from a no-reply address",
}

_NOREPLY_RE = re.compile(
    r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|donotreply|mailer[-_.]daemon|bounce[s]?)(?:[-_.+].*)?@"
)


def bulk_signals(mail: ParsedEmail) -> list[str]:
    """Which bulk kinds fire for this email, as BULK_KINDS keys."""
    out: list[str] = []
    if mail.header("list-unsubscribe") or mail.header("list-id"):
        out.append("newsletter")
    precedence = mail.header("precedence").lower()
    auto = mail.header("auto-submitted").lower()
    if (precedence in ("bulk", "list", "junk") or (auto and auto != "no")
            or mail.header("feedback-id")):
        out.append("bulk")
    if _NOREPLY_RE.match(mail.from_addr):
        out.append("noreply")
    return out
