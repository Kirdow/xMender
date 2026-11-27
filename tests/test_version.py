"""Build footer info."""

from __future__ import annotations

import subprocess

from xmender import version


def test_build_info_from_git(monkeypatch):
    calls = {
        ("log", "-1", "--format=%H%n%cI"): "a" * 40 + "\n2026-11-27T10:00:00+01:00",
        ("status", "--porcelain", "--untracked-files=no"): " M xmender/app.py",
        ("remote", "get-url", "origin"): "git@github.com:Someone/Fork.git",
    }
    monkeypatch.setattr(version, "_git", lambda *a: calls.get(a))
    version.build_info.cache_clear()
    try:
        b = version.build_info()
    finally:
        version.build_info.cache_clear()
    assert b == {
        "commit": "a" * 40,
        "date": "2026-11-27T10:00:00+01:00",
        "dirty": True,
        "url": "https://github.com/Someone/Fork/commit/" + "a" * 40,
    }


def test_build_info_without_git(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    version.build_info.cache_clear()
    try:
        assert version.build_info() == {"commit": None, "date": None, "dirty": None, "url": None}
    finally:
        version.build_info.cache_clear()


def test_repo_url_fallback(monkeypatch):
    monkeypatch.setattr(version, "_git", lambda *a: "https://gitlab.com/x/y.git")
    assert version._repo_url() == version.REPO_URL
    monkeypatch.setattr(version, "_git", lambda *a: "https://github.com/Kirdow/xMender")
    assert version._repo_url() == "https://github.com/Kirdow/xMender"
