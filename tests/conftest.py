import os
import re
import tempfile

import pytest

_DATA = tempfile.mkdtemp(prefix="xmender-test-")
os.environ["XMENDER_DATA_DIR"] = _DATA
os.environ.pop("XMENDER_DATABASE_URL", None)
os.environ.pop("XMENDER_SECRET_KEY", None)


@pytest.fixture(scope="session")
def app_client():
    from fastapi.testclient import TestClient

    from xmender.app import create_app

    with TestClient(create_app(start_poller=False), headers={"x-xmender": "1"}) as c:
        yield c


@pytest.fixture(scope="session")
def admin(app_client, capsys_session):
    """Completes first-time setup and returns a logged-in client."""
    out = capsys_session
    temp = re.search(r"Temporary password: (\S+)", out).group(1)
    r = app_client.post(
        "/api/auth/setup", json={"temp_password": temp, "new_password": "correct-horse-1"}
    )
    assert r.status_code == 200, r.text
    return app_client


@pytest.fixture(scope="session")
def capsys_session(app_client):
    # ensure_admin printed during app startup; regenerate deterministically
    # by forcing a new temp password and capturing it.
    import io
    import sys

    from xmender.bootstrap import ensure_admin

    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        ensure_admin()
    finally:
        sys.stdout = old
    return buf.getvalue()
