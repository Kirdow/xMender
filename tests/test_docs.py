"""User docs: served publicly at /docs and from /static/docs/."""

from __future__ import annotations


def test_docs_page_is_public(app_client):
    from fastapi.testclient import TestClient

    anon = TestClient(app_client.app)  # no session cookie
    r = anon.get("/docs")
    assert r.status_code == 200
    assert "docs.js" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]
    idx = anon.get("/static/docs/index.json")
    assert idx.status_code == 200
    first = idx.json()["groups"][0]["sections"][0]
    assert anon.get(f"/static/docs/{first['file']}").status_code == 200
