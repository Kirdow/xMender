"""Gmail over IMAP (receiving) and SMTP (sending, optional).

All functions here are blocking; call them through `asyncio.to_thread`.
"""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
APP_PASSWORDS_URL = "https://myaccount.google.com/apppasswords"

TIMEOUT = 30

# Gmail local parts are letters, digits and dots. `+` aliases are rejected.
_GMAIL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.]{0,62}[a-z0-9])?@(?:gmail\.com|googlemail\.com)$")


class GmailError(Exception):
    """User-presentable failure."""


def normalize_gmail(address: str) -> str:
    addr = (address or "").strip().lower()
    if "+" in addr:
        raise GmailError("Use the plain Gmail address, without a `+` alias.")
    if not _GMAIL_RE.match(addr):
        raise GmailError("Enter a valid @gmail.com address.")
    return addr


def normalize_app_password(value: str) -> str:
    # Google shows app passwords as four groups of four, separated by spaces.
    pw = re.sub(r"\s+", "", value or "")
    if not pw:
        raise GmailError("App password is required.")
    return pw


@dataclass(frozen=True)
class Account:
    email: str
    password: str
    imap_host: str = IMAP_HOST
    imap_port: int = IMAP_PORT
    smtp_host: str = SMTP_HOST
    smtp_port: int = SMTP_PORT


def _imap_login(acct: Account) -> imaplib.IMAP4_SSL:
    try:
        conn = imaplib.IMAP4_SSL(
            acct.imap_host, acct.imap_port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT
        )
    except (OSError, socket.timeout) as e:
        raise GmailError(f"IMAP: cannot connect to {acct.imap_host}:{acct.imap_port} ({e}).") from e
    try:
        conn.login(acct.email, acct.password)
    except imaplib.IMAP4.error as e:
        _safe_logout(conn)
        raise GmailError(
            "IMAP: login rejected. Check the address and that the app password is correct."
        ) from e
    return conn


def _safe_logout(conn: imaplib.IMAP4) -> None:
    try:
        conn.logout()
    except Exception:
        pass


def _status(conn: imaplib.IMAP4_SSL) -> tuple[int, int]:
    typ, data = conn.status("INBOX", "(UIDVALIDITY UIDNEXT)")
    if typ != "OK" or not data or not data[0]:
        raise GmailError("IMAP: could not read INBOX status.")
    text = data[0].decode(errors="replace") if isinstance(data[0], bytes) else str(data[0])
    validity = re.search(r"UIDVALIDITY (\d+)", text)
    nxt = re.search(r"UIDNEXT (\d+)", text)
    if not validity or not nxt:
        raise GmailError("IMAP: unexpected INBOX status reply.")
    return int(validity.group(1)), int(nxt.group(1))


def test_imap(acct: Account) -> tuple[int, int]:
    """Log in and read the INBOX cursor. Returns (uidvalidity, last_uid)."""
    conn = _imap_login(acct)
    try:
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise GmailError("IMAP: could not open INBOX.")
        validity, uidnext = _status(conn)
        return validity, uidnext - 1
    finally:
        _safe_logout(conn)


def test_smtp(acct: Account) -> None:
    """Log in to SMTP over SSL. Never sends anything."""
    try:
        with smtplib.SMTP_SSL(
            acct.smtp_host, acct.smtp_port, context=ssl.create_default_context(), timeout=TIMEOUT
        ) as s:
            s.login(acct.email, acct.password)
    except smtplib.SMTPAuthenticationError as e:
        raise GmailError("SMTP: login rejected. Check the address and app password.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise GmailError(f"SMTP: cannot connect to {acct.smtp_host}:{acct.smtp_port} ({e}).") from e


# Gmail inbox categories, searchable with X-GM-RAW "category:<name>".
CATEGORIES = ("primary", "social", "promotions", "updates", "forums")


@dataclass
class FetchResult:
    uidvalidity: int
    last_uid: int
    messages: list[tuple[int, bytes]] = field(default_factory=list)
    reset: bool = False
    pending: int = 0
    # uid -> {"labels": [...], "category": str}; only on Gmail (X-GM-EXT-1).
    gmail_meta: dict[int, dict] = field(default_factory=dict)


def fetch_new(acct: Account, uidvalidity: int | None, last_uid: int | None, limit: int) -> FetchResult:
    """Fetch messages that arrived after `last_uid`, oldest first, without
    marking them read. If the cursor is missing or the mailbox was rebuilt
    (UIDVALIDITY changed), the cursor is reset to "now" and nothing is fetched."""
    conn = _imap_login(acct)
    try:
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise GmailError("IMAP: could not open INBOX.")
        validity, uidnext = _status(conn)
        if last_uid is None or uidvalidity != validity:
            return FetchResult(uidvalidity=validity, last_uid=uidnext - 1, reset=True)
        if uidnext - 1 <= last_uid:
            return FetchResult(uidvalidity=validity, last_uid=last_uid)

        typ, data = conn.uid("SEARCH", None, f"UID {last_uid + 1}:*")
        if typ != "OK":
            raise GmailError("IMAP: search failed.")
        uids = sorted(int(u) for u in (data[0] or b"").split() if int(u) > last_uid)
        result = FetchResult(uidvalidity=validity, last_uid=last_uid, pending=max(0, len(uids) - limit))
        is_gmail = _has_gmail_ext(conn)
        items = "(BODY.PEEK[] X-GM-LABELS)" if is_gmail else "(BODY.PEEK[])"
        for uid in uids[:limit]:
            typ, parts = conn.uid("FETCH", str(uid), items)
            if typ != "OK":
                raise GmailError(f"IMAP: fetching UID {uid} failed.")
            raw = next((p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), None)
            if raw is not None:
                result.messages.append((uid, raw))
                if is_gmail:
                    result.gmail_meta[uid] = {"labels": parse_labels(parts)}
        if is_gmail and result.messages:
            _add_categories(conn, result)
        return result
    finally:
        _safe_logout(conn)


def _has_gmail_ext(conn: imaplib.IMAP4) -> bool:
    try:
        return "X-GM-EXT-1" in (conn.capabilities or ())
    except Exception:
        return False


def _add_categories(conn: imaplib.IMAP4, result: FetchResult) -> None:
    """Fill `category` for fetched messages with one search per category.
    Failures leave the category unknown rather than failing the poll."""
    uids = [u for u, _ in result.messages]
    span = f"{min(uids)}:{max(uids)}"
    found: dict[int, str] = {}
    try:
        for cat in CATEGORIES[1:]:
            typ, data = conn.uid("SEARCH", None, "UID", span, "X-GM-RAW", f'"category:{cat}"')
            if typ != "OK":
                return
            for u in (data[0] or b"").split():
                found.setdefault(int(u), cat)
    except (imaplib.IMAP4.error, OSError, ValueError):
        return
    for uid in uids:
        if uid in result.gmail_meta:
            result.gmail_meta[uid]["category"] = found.get(uid, "primary")


def _imap_utf7_decode(s: str) -> str:
    """Decode IMAP modified UTF-7 (RFC 3501 5.1.3), used for label names."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "&":
            j = s.find("-", i)
            if j < 0:
                out.append(s[i:])
                break
            chunk = s[i + 1:j]
            if not chunk:
                out.append("&")
            else:
                b64 = chunk.replace(",", "/")
                b64 += "=" * (-len(b64) % 4)
                try:
                    out.append(base64.b64decode(b64).decode("utf-16-be"))
                except Exception:
                    out.append(s[i:j + 1])
            i = j + 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_labels(parts: list) -> list[str]:
    """Labels from a FETCH response containing X-GM-LABELS (...). System
    labels keep their backslash (\\Inbox, \\Important)."""
    text = ""
    for p in parts:
        chunk = p[0] if isinstance(p, tuple) else p
        if isinstance(chunk, bytes):
            text += chunk.decode("utf-8", "replace") + " "
    start = text.find("X-GM-LABELS (")
    if start < 0:
        return []
    i = start + len("X-GM-LABELS (")
    labels: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == ")":
            break
        if ch == " ":
            i += 1
        elif ch == '"':
            j, buf = i + 1, []
            while j < len(text) and text[j] != '"':
                if text[j] == "\\" and j + 1 < len(text):
                    j += 1
                buf.append(text[j])
                j += 1
            labels.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < len(text) and text[j] not in " )":
                j += 1
            labels.append(text[i:j])
            i = j
    return [_imap_utf7_decode(lb) for lb in labels if lb]


# --- Parsing -----------------------------------------------------------------


class _HTMLText(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _HTMLText()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(p.out)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


@dataclass
class Attachment:
    name: str
    content_type: str
    size: int
    data: bytes = field(default=b"", repr=False)

    @property
    def extension(self) -> str:
        _, dot, ext = self.name.rpartition(".")
        return ext.lower() if dot else ""

    def describe(self) -> str:
        return f"{self.name} ({self.content_type}, {human_size(self.size)})"


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


@dataclass
class ParsedEmail:
    message_id: str | None
    sender: str
    to: str
    cc: str
    subject: str
    date: datetime | None
    body: str
    attachments: list[Attachment]
    # Lowercased header name -> every value, in message order.
    headers: dict[str, list[str]] = field(default_factory=dict)
    # Gmail only, set by the poller from the IMAP fetch; None when unknown.
    labels: list[str] | None = None
    category: str | None = None

    @property
    def has_attachment(self) -> bool:
        return bool(self.attachments)

    @property
    def from_addr(self) -> str:
        return parseaddr(self.sender)[1].strip().lower()

    @property
    def from_name(self) -> str:
        return parseaddr(self.sender)[0].strip()

    def header(self, name: str) -> str:
        """First value of a header, or ''."""
        vals = self.headers.get(name.lower())
        return vals[0] if vals else ""

    def snippet(self, n: int = 300) -> str:
        s = re.sub(r"\s+", " ", self.body).strip()
        return s if len(s) <= n else s[: n - 1] + "…"


def _header(msg: EmailMessage, name: str) -> str:
    try:
        v = msg.get(name)
        return str(v).strip() if v is not None else ""
    except Exception:
        raw = msg.get_all(name, failobj=[])
        return " ".join(str(x) for x in raw).strip()


def parse_email(raw: bytes) -> ParsedEmail:
    msg: EmailMessage = email.message_from_bytes(raw, policy=policy.default)  # type: ignore[assignment]

    body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            content = part.get_content()
            body = html_to_text(content) if part.get_content_type() == "text/html" else content
    except Exception:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            body = payload.decode(errors="replace")

    attachments: list[Attachment] = []
    try:
        for att in msg.iter_attachments():
            try:
                data = att.get_payload(decode=True) or b""
            except Exception:
                data = b""
            if not isinstance(data, bytes):
                data = b""
            ctype = att.get_content_type()
            attachments.append(
                Attachment(name=att.get_filename() or ctype, content_type=ctype, size=len(data), data=data)
            )
    except Exception:
        pass

    headers: dict[str, list[str]] = {}
    for key in set(msg.keys()):
        vals: list[str] = []
        for raw_val in msg.get_all(key, failobj=[]):
            try:
                vals.append(str(raw_val).strip())
            except Exception:
                continue
        headers[key.lower()] = vals

    date = None
    try:
        if msg.get("Date"):
            date = parsedate_to_datetime(_header(msg, "Date"))
    except Exception:
        date = None

    return ParsedEmail(
        message_id=_header(msg, "Message-ID") or None,
        sender=_header(msg, "From"),
        to=_header(msg, "To"),
        cc=_header(msg, "Cc"),
        subject=_header(msg, "Subject"),
        date=date,
        body=(body or "").strip(),
        attachments=attachments,
        headers=headers,
    )
