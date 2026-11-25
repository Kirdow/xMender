"""Discord webhook delivery.

Webhook URLs come in several historical shapes (discordapp.com, canary/ptb
hosts, with or without `/api/vNN`). They are normalised to the current
`https://discord.com/api/v10/webhooks/{id}/{token}` form. Messages are sent as
classic embeds: Components V2 messages (`flags=IS_COMPONENTS_V2`, needing
`?with_components=true`) cannot carry embeds at all, so they are not used.
Forum/media channels require a thread; that case is handled by retrying with
`thread_name`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx

API_BASE = "https://discord.com/api/v10"
EMBED_TITLE = "xMender Notification"
EMBED_COLOR = 0x00FFFF  # bright aqua
EMBED_DESCRIPTION_LIMIT = 4096
USERNAME_LIMIT = 80

_URL_RE = re.compile(
    r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/(\d{5,25})/([A-Za-z0-9_\-]{20,200})/?$"
)
# Discord error code: forum/media channel webhooks need thread_name or thread_id.
_NEEDS_THREAD = 220001


class DiscordError(Exception):
    """User-presentable failure."""


@dataclass(frozen=True)
class Webhook:
    id: str
    token: str
    thread_id: str | None = None

    @property
    def url(self) -> str:
        return f"{API_BASE}/webhooks/{self.id}/{self.token}"


def parse_webhook_url(value: str) -> Webhook:
    raw = (value or "").strip()
    parts = urlsplit(raw)
    base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    m = _URL_RE.match(base)
    if not m:
        raise DiscordError(
            "Not a Discord webhook URL. Expected https://discord.com/api/webhooks/<id>/<token>."
        )
    thread = parse_qs(parts.query).get("thread_id", [None])[0]
    if thread is not None and not thread.isdigit():
        raise DiscordError("thread_id in the webhook URL must be numeric.")
    return Webhook(id=m.group(1), token=m.group(2), thread_id=thread)


def canonical_url(hook: Webhook) -> str:
    return hook.url + (f"?thread_id={hook.thread_id}" if hook.thread_id else "")


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def send_embed(
    webhook_url: str,
    *,
    username: str,
    description: str,
    footer: str | None = None,
    thread_name: str | None = None,
) -> None:
    """Post one embed. Blocking; raises DiscordError on failure."""
    hook = parse_webhook_url(webhook_url)
    embed: dict = {
        "title": EMBED_TITLE,
        "description": clip(description.strip() or "(empty)", EMBED_DESCRIPTION_LIMIT),
        "color": EMBED_COLOR,
    }
    if footer:
        embed["footer"] = {"text": clip(footer, 2048)}
    payload: dict = {
        "embeds": [embed],
        # Never ping anyone, whatever the generated text contains.
        "allowed_mentions": {"parse": []},
    }
    if username:
        payload["username"] = clip(username, USERNAME_LIMIT)

    params: dict = {"wait": "true"}
    if hook.thread_id:
        params["thread_id"] = hook.thread_id

    with httpx.Client(timeout=20) as client:
        for attempt in range(3):
            try:
                r = client.post(hook.url, params=params, json=payload)
            except httpx.HTTPError as e:
                raise DiscordError(f"Could not reach Discord ({e}).") from e

            if r.status_code == 429 and attempt < 2:
                try:
                    wait = float(r.json().get("retry_after", 1))
                except Exception:
                    wait = 1.0
                time.sleep(min(wait, 10))
                continue
            if r.status_code == 400 and "thread_name" not in payload and _error_code(r) == _NEEDS_THREAD:
                payload["thread_name"] = clip(thread_name or EMBED_TITLE, 100)
                continue
            if r.is_success:
                return
            if r.status_code in (401, 404):
                raise DiscordError("Discord rejected the webhook (deleted or wrong token).")
            raise DiscordError(f"Discord returned HTTP {r.status_code}: {_error_text(r)}")
    raise DiscordError("Discord kept rate-limiting the webhook.")


def _error_code(r: httpx.Response) -> int | None:
    try:
        return int(r.json().get("code"))
    except Exception:
        return None


def _flatten_errors(node, path: str = "") -> list[str]:
    """Discord's 50035 body: {"errors": {"embeds": {"0": {"description":
    {"_errors": [{"code": ..., "message": ...}]}}}}} -> ["embeds.0.description: ..."]."""
    out: list[str] = []
    if isinstance(node, dict):
        for err in node.get("_errors", []) or []:
            if isinstance(err, dict):
                out.append(f"{path or 'body'}: {err.get('message') or err.get('code')}")
        for key, child in node.items():
            if key != "_errors":
                out.extend(_flatten_errors(child, f"{path}.{key}" if path else str(key)))
    return out


def _error_text(r: httpx.Response) -> str:
    try:
        data = r.json()
    except Exception:
        return r.text[:300]
    msg = str(data.get("message", r.text))
    details = _flatten_errors(data.get("errors") or {})
    if details:
        msg += " (" + "; ".join(details) + ")"
    return msg[:600]


# Discord refuses webhook usernames containing these (case-insensitive).
_FORBIDDEN_NAME_PARTS = ("discord", "clyde")
_FORBIDDEN_NAMES = ("everyone", "here")


def username_problem(name: str) -> str | None:
    n = name.strip().lower()
    if not n:
        return "Name is required."
    if len(n) > USERNAME_LIMIT:
        return f"Name must be at most {USERNAME_LIMIT} characters."
    if any(p in n for p in _FORBIDDEN_NAME_PARTS):
        return 'Discord does not allow "discord" or "clyde" in webhook names.'
    if n in _FORBIDDEN_NAMES:
        return f'Discord does not allow "{name.strip()}" as a webhook name.'
    return None
