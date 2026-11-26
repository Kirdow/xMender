"""Generic HTTP webhooks: POST/PUT a JSON or text body to a user's URL.

Safety:
- Only http/https, no credentials in the URL (use headers), no redirects.
- The host is resolved once and every address must be public unless
  `XMENDER_HTTP_ALLOW_PRIVATE` is on. The request then connects to that
  resolved address (TLS still verifies the real host name), so DNS cannot
  switch to an internal address between the check and the request.
- URLs and header values are secrets: they never appear in errors or logs;
  only the host does.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

TIMEOUT = 15
MAX_BODY = 256 * 1024
METHODS = ("POST", "PUT")
CONTENT_TYPES = {"json": "application/json", "text": "text/plain; charset=utf-8"}
MAX_HEADERS = 10
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
_BLOCKED_HEADERS = {
    "host", "content-length", "transfer-encoding", "connection", "content-type",
    "upgrade", "te", "trailer", "keep-alive", "proxy-authorization", "proxy-connection",
}


# Shared address space (e.g. Tailscale) counts as a private network.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class HttpHookError(Exception):
    """User-presentable failure."""


@dataclass(frozen=True)
class Target:
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""


def normalize_url(value: str) -> str:
    raw = (value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise HttpHookError("The URL must start with https:// (or http://).")
    if not parts.hostname:
        raise HttpHookError("The URL has no host.")
    if parts.username or parts.password:
        raise HttpHookError("Put credentials in a header, not in the URL.")
    if len(raw) > 2000:
        raise HttpHookError("The URL is too long.")
    try:
        parts.port  # noqa: B018  (validates the port)
    except ValueError as e:
        raise HttpHookError("The URL has an invalid port.") from e
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def normalize_headers(items: object) -> dict[str, str]:
    """From [{"name", "value"}] or {name: value}. Raises HttpHookError."""
    pairs: list[tuple[str, str]] = []
    if isinstance(items, dict):
        pairs = [(str(k), str(v)) for k, v in items.items()]
    elif isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and str(it.get("name") or "").strip():
                pairs.append((str(it.get("name")), str(it.get("value") or "")))
    out: dict[str, str] = {}
    for name, value in pairs:
        name = name.strip()
        if not _HEADER_NAME.match(name):
            raise HttpHookError(f"`{name[:64]}` is not a valid header name.")
        if name.lower() in _BLOCKED_HEADERS:
            raise HttpHookError(f"The `{name}` header is set by xMender and cannot be changed.")
        if "\r" in value or "\n" in value or len(value) > 4000:
            raise HttpHookError(f"The value of `{name}` is invalid.")
        out[name] = value.strip()
    if len(out) > MAX_HEADERS:
        raise HttpHookError(f"At most {MAX_HEADERS} headers.")
    return out


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_private: bool, host: str) -> None:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_multicast or ip.is_unspecified:
        raise HttpHookError(f"{host} resolves to an address that cannot be used.")
    if ip.is_global:
        return
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip in _CGNAT:
        if allow_private:
            return
        raise HttpHookError(
            f"{host} is on this machine or a private network. That is blocked unless the "
            "server owner sets XMENDER_HTTP_ALLOW_PRIVATE=true."
        )
    raise HttpHookError(f"{host} resolves to an address that cannot be used.")


def resolve(host: str, port: int, allow_private: bool) -> str:
    """Resolve `host` and return one checked address. All addresses are
    checked, so a name with one public and one private address is refused."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _check_ip(literal, allow_private, host)
        return str(literal)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise HttpHookError(f"Cannot resolve {host}.") from e
    addrs = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        _check_ip(ip, allow_private, host)
        addrs.append(ip)
    if not addrs:
        raise HttpHookError(f"Cannot resolve {host}.")
    return str(addrs[0])


def check_url(url: str, allow_private: bool) -> str:
    """Resolve and check the URL's host; returns the address to connect to."""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return resolve(parts.hostname or "", port, allow_private)


def _pinned(url: str, ip: str) -> str:
    parts = urlsplit(url)
    host_part = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host_part}:{parts.port}" if parts.port else host_part
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))


def encode_body(content_type: str, body: object) -> bytes:
    data = (json.dumps(body, ensure_ascii=False) if content_type == "json" else str(body)).encode()
    if len(data) > MAX_BODY:
        raise HttpHookError(f"The request body is larger than {MAX_BODY // 1024} KB.")
    return data


def send(target: Target, *, method: str, content_type: str, body: object,
         allow_private: bool) -> int:
    """Send one request; returns the HTTP status. Blocking. Raises HttpHookError."""
    url = normalize_url(target.url)
    parts = urlsplit(url)
    host = parts.hostname or ""
    data = encode_body(content_type, body)
    ip = check_url(url, allow_private)
    headers = {
        **target.headers,
        "Host": parts.netloc,
        "Content-Type": CONTENT_TYPES[content_type],
        "User-Agent": "xMender",
    }
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}

    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as client:
        for attempt in range(2):
            try:
                r = client.request(method, _pinned(url, ip), content=data, headers=headers,
                                   extensions=extensions)
            except httpx.TimeoutException as e:
                raise HttpHookError(f"{host} did not answer within {TIMEOUT} s.") from e
            except httpx.HTTPError as e:
                raise HttpHookError(f"Could not reach {host} ({type(e).__name__}).") from e
            if r.status_code in (429, 502, 503, 504) and attempt == 0:
                try:
                    wait = float(r.headers.get("retry-after", "1"))
                except ValueError:
                    wait = 1.0
                time.sleep(max(0.0, min(wait, 5.0)))
                continue
            if 300 <= r.status_code < 400:
                raise HttpHookError(
                    f"{host} answered with a redirect (HTTP {r.status_code}); redirects are not "
                    "followed. Use the final URL."
                )
            if not r.is_success:
                raise HttpHookError(f"{host} returned HTTP {r.status_code}.")
            return r.status_code
    raise HttpHookError(f"{host} kept answering HTTP {r.status_code}.")
