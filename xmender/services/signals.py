"""Header-based signals about an email: bulk/newsletter and phishing hints.

Everything here is deterministic and uses only the parsed message, so it is
free to run before any LLM step.
"""

from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Any

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


# --- phishing ----------------------------------------------------------------

PHISHING_KINDS = {
    "auth_fail": "Gmail's SPF, DKIM or DMARC check failed",
    "reply_to_mismatch": "Reply-To goes to a different domain than From",
    "name_has_address": "Display name contains a different email address",
    "brand_mismatch": "Mentions a protected name but comes from another domain",
    "free_mail": "Sent from a free email provider",
}
# Only Gmail's own verdict is trusted; senders can add their own headers.
TRUSTED_AUTHSERV = "mx.google.com"

FREE_MAIL = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me",
    "protonmail.com", "pm.me", "gmx.com", "gmx.net", "gmx.de", "mail.com", "yandex.com",
    "yandex.ru", "zoho.com", "tutanota.com", "tuta.io", "mail.ru", "qq.com", "163.com",
}
_SECOND_LEVEL = {"co", "com", "net", "org", "gov", "ac", "edu", "ne", "or", "go"}
_ADDR_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_AUTH_RE = re.compile(r"\b(spf|dkim|dmarc)=(\w+)", re.IGNORECASE)


def domain_of(addr: str) -> str:
    return addr.rpartition("@")[2].strip().lower().rstrip(".") if "@" in addr else ""


def org_domain(domain: str) -> str:
    """Rough registrable domain: last two labels, or three for `co.uk`-style."""
    labels = [x for x in domain.lower().split(".") if x]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _same_org(a: str, b: str) -> bool:
    return bool(a) and bool(b) and org_domain(a) == org_domain(b)


def auth_results(mail: ParsedEmail) -> dict[str, str] | None:
    """Gmail's own SPF/DKIM/DMARC verdicts (lowercased), or None if absent.
    The topmost header from mx.google.com is Gmail's; later ones may be forged."""
    for value in mail.headers.get("authentication-results", []):
        authserv = value.split(";", 1)[0].strip().lower()
        if authserv == TRUSTED_AUTHSERV:
            out: dict[str, str] = {}
            for method, result in _AUTH_RE.findall(value):
                out.setdefault(method.lower(), result.lower())
            return out
    return None


def parse_brands(text: str) -> list[dict[str, Any]]:
    """Lines of `Name = domain, domain`. Raises ValueError with a readable message."""
    out: list[dict[str, Any]] = []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        name, eq, doms = line.partition("=")
        domains = [d.strip().lower().lstrip("@") for d in doms.split(",") if d.strip()]
        if not eq or not name.strip() or not domains:
            raise ValueError(f"protected names line {n}: use `Name = domain.com, other.com`.")
        if any(not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d) for d in domains):
            raise ValueError(f"protected names line {n}: invalid domain.")
        out.append({"name": name.strip()[:100], "domains": domains[:20]})
    return out[:50]


def phishing_signals(mail: ParsedEmail, brands: list[dict[str, Any]] | None = None) -> list[str]:
    """Which PHISHING_KINDS fire for this email."""
    out: list[str] = []
    from_dom = domain_of(mail.from_addr)

    auth = auth_results(mail)
    if auth and (auth.get("spf") in ("fail", "softfail") or auth.get("dkim") == "fail"
                 or auth.get("dmarc") == "fail"):
        out.append("auth_fail")

    reply_to = parseaddr(mail.header("reply-to"))[1]
    if reply_to and from_dom and not _same_org(domain_of(reply_to), from_dom):
        out.append("reply_to_mismatch")

    for dom in _ADDR_RE.findall(mail.from_name):
        if not _same_org(dom.lower(), from_dom):
            out.append("name_has_address")
            break

    hay = f"{mail.from_name}\n{mail.subject}".lower()
    for b in brands or []:
        if b["name"].lower() in hay and not any(
            from_dom == d or from_dom.endswith("." + d) for d in b["domains"]
        ):
            out.append("brand_mismatch")
            break

    if from_dom in FREE_MAIL:
        out.append("free_mail")
    return out
