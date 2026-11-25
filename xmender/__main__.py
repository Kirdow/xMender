"""Entry point: `python -m xmender`."""

from __future__ import annotations

import logging
import os

import uvicorn

from .app import create_app
from .config import get_settings


def main() -> None:
    # Database, secret key and logs hold credentials: keep them owner-only.
    os.umask(0o077)
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)
    # httpx logs every request URL at INFO, which would leak webhook tokens.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    if settings.allow_external_access:
        logging.getLogger("xmender").warning(
            "XMENDER_ALLOW_EXTERNAL_ACCESS is on: listening on all interfaces"
        )
    uvicorn.run(
        create_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
