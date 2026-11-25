"""First-start setup of the built-in admin account."""

from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from .db import session_scope
from .models import User
from .security import generate_temp_password, hash_password

log = logging.getLogger(__name__)

ADMIN_USERNAME = "admin"


def ensure_admin() -> None:
    """Create `admin` if missing. While its setup is unfinished, issue a fresh
    temporary password on every start and print it to stdout."""
    with session_scope() as db:
        admin = db.scalar(select(User).where(User.is_root.is_(True)))
        if admin is not None and not admin.must_change_password:
            return

        temp = generate_temp_password()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(temp),
                is_root=True,
                is_admin=True,
                permissions=[],
                must_change_password=True,
            )
            db.add(admin)
        else:
            admin.password_hash = hash_password(temp)

    bar = "=" * 64
    print(
        f"\n{bar}\n"
        f" xMender first-time setup\n"
        f" Open the web UI and finish setting up the `{ADMIN_USERNAME}` account.\n"
        f" Temporary password: {temp}\n"
        f" (A new one is issued on each start until setup is finished.)\n"
        f"{bar}\n",
        file=sys.stdout,
        flush=True,
    )
    log.info("Admin setup pending; temporary password printed to stdout")
