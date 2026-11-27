"""Build info: the git commit this instance runs, read once at startup."""

from __future__ import annotations

import logging
import re
import subprocess
from functools import lru_cache

from .config import PROJECT_ROOT

REPO_URL = "https://github.com/Kirdow/xMender"

log = logging.getLogger(__name__)

_GITHUB_REMOTE = re.compile(r"^(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)"
                            r"([\w.-]+/[\w.-]+?)(?:\.git)?/?$")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            capture_output=True, text=True, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def _repo_url() -> str:
    remote = _git("remote", "get-url", "origin") or ""
    m = _GITHUB_REMOTE.match(remote)
    return f"https://github.com/{m.group(1)}" if m else REPO_URL


@lru_cache(maxsize=1)
def build_info() -> dict:
    """`{commit, date, dirty, url}`; all None when this is not a git checkout.

    Cached, so it reports the code loaded at startup even after a later `git pull`.
    """
    head = _git("log", "-1", "--format=%H%n%cI")
    if not head or "\n" not in head:
        log.info("Build info unavailable (not a git checkout or git missing).")
        return {"commit": None, "date": None, "dirty": None, "url": None}
    commit, date = head.split("\n", 1)
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "commit": commit,
        "date": date,
        "dirty": bool(status) if status is not None else None,
        "url": f"{_repo_url()}/commit/{commit}",
    }
