"""User docs: served publicly at /docs, and kept in step with the code.

The docs are Markdown under xmender/web/static/docs/, rendered by docs.js for
both the in-app modal and the /docs page. These tests fail when the code gains
something user-visible the docs do not mention, or when a doc link breaks.
See .claude/skills/docs-maintenance/SKILL.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from xmender import models
from xmender.services import chains, gmail, pipeline, signals, template
from xmender.services.steps import REGISTRY

STATIC = Path(__file__).resolve().parent.parent / "xmender" / "web" / "static"
DOCS = STATIC / "docs"
APP_JS = (STATIC / "app.js").read_text()

HEADING = re.compile(r"^(#{1,4})\s+(.*?)(?:\s+\{#([a-z0-9_-]+)\})?\s*$")
DOC_LINK = re.compile(r"\]\(#([^)\s]*)\)")


def slug(text: str) -> str:
    """Mirror of slug() in docs.js."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _index() -> list[dict]:
    data = json.loads((DOCS / "index.json").read_text())
    return [s for g in data["groups"] for s in g["sections"]]


def _text(section_id: str) -> str:
    meta = next(s for s in _index() if s["id"] == section_id)
    return (DOCS / meta["file"]).read_text()


def _anchors(md: str) -> dict[str, str]:
    """heading id -> heading text, for ## and deeper, outside code blocks."""
    out, in_code = {}, False
    for line in md.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        m = HEADING.match(line)
        if m and not in_code and len(m.group(1)) > 1:
            out[m.group(3) or slug(m.group(2))] = m.group(2)
    return out


def _block(md: str, anchor: str) -> str:
    """Text under the heading with this id, up to the next heading of the same or higher level."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m and (m.group(3) or slug(m.group(2))) == anchor:
            level = len(m.group(1))
            body = []
            for nxt in lines[i + 1:]:
                n = HEADING.match(nxt)
                if n and len(n.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    raise AssertionError(f"no heading {{#{anchor}}}")


def _js_list(name: str) -> list[str]:
    m = re.search(rf"const {name} = \[(.*?)\];", APP_JS, re.S)
    assert m, f"{name} not found in app.js"
    return re.findall(r"'([^']+)'", m.group(1))


# --- serving -----------------------------------------------------------------


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


# --- structure ---------------------------------------------------------------


def test_index_matches_files():
    index = _index()
    ids = [s["id"] for s in index]
    assert len(ids) == len(set(ids)), "duplicate section id"
    listed = {s["file"] for s in index}
    on_disk = {p.name for p in DOCS.glob("*.md")}
    assert listed == on_disk, f"not in index.json: {on_disk - listed}; missing files: {listed - on_disk}"
    for s in index:
        assert re.fullmatch(r"[a-z0-9-]+", s["id"]), s["id"]
        first = (DOCS / s["file"]).read_text().splitlines()[0]
        assert first == f"# {s['title']}", f"{s['file']} must start with '# {s['title']}'"


def test_heading_ids_unique_per_section():
    for s in _index():
        md = _text(s["id"])
        ids = [m.group(3) or slug(m.group(2)) for line in md.splitlines() if (m := HEADING.match(line)) and len(m.group(1)) > 1]
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"{s['file']}: duplicate heading ids {dupes}; add {{#id}}"


def _link_targets() -> list[tuple[str, str]]:
    out = [(s["file"], target) for s in _index() for target in DOC_LINK.findall(_text(s["id"]))]
    out += [("app.js", t) for t in re.findall(r"(?:openDocs|docsLink)\('([^']+)'", APP_JS)]
    out += [("app.js", f"steps/{t}") for t in REGISTRY]  # the per-step "?" button
    return out


@pytest.mark.parametrize("source,target", _link_targets())
def test_doc_links_resolve(source, target):
    sec, _, anchor = target.partition("/")
    sections = {s["id"] for s in _index()}
    assert sec in sections, f"{source}: link to unknown section #{target}"
    if anchor:
        assert anchor in _anchors(_text(sec)), f"{source}: #{target} has no heading with that id"


# --- the docs cover what the code offers -------------------------------------


def test_every_step_type_documented():
    md = _text("steps")
    anchors = _anchors(md)
    for t, d in REGISTRY.items():
        assert t in anchors, f"steps.md: add a heading '### {d.label} {{#{t}}}'"
        assert anchors[t] == d.label, f"steps.md: heading for {t} should read {d.label!r}"
        block = _block(md, t)
        outs = set(d.outputs({"fields": []}))
        for out in sorted(outs):
            assert f"`{out}`" in block, f"steps.md {t}: output `{out}` not documented"
        summary = next(line for line in md.splitlines() if f"(#steps/{t})" in line)
        expected = (["matched"] if d.group == "filter" else []) + sorted(outs)
        for out in expected:
            assert f"`{out}`" in summary, f"steps.md summary table, {t}: missing `{out}`"


def test_signal_kinds_documented():
    md = _text("steps")
    for label in [*signals.BULK_KINDS.values(), *signals.PHISHING_KINDS.values()]:
        assert label in md, f"steps.md: list the checkbox {label!r}"
    for key in [*signals.BULK_KINDS, *signals.PHISHING_KINDS, *gmail.CATEGORIES]:
        assert f"`{key}`" in md, f"steps.md: mention `{key}`"


def test_email_fields_and_modifiers_documented():
    md = _text("placeholders")
    for f in template.EMAIL_FIELDS:
        assert f"{{{{email.{f}}}}}" in md, f"placeholders.md: document {{{{email.{f}}}}}"
    for mod in template.MODIFIERS:
        assert re.search(rf"`{mod}(:[^`]*)?`", md), f"placeholders.md: document the `{mod}` modifier"


def test_frontend_email_fields_match_backend():
    assert _js_list("EMAIL_FIELDS") == list(template.EMAIL_FIELDS)


def test_conditions_documented():
    md = _text("step-options")
    labels = re.findall(r"\['[a-z_]+', '([^']+)'\]", re.search(r"const COND_OPS = \[(.*?)\];", APP_JS, re.S).group(1))
    assert len(labels) == len(pipeline.OPS) - 2, "COND_OPS in app.js and pipeline.OPS differ"
    for label in [*labels, "matched", "did not match"]:
        assert f"| {label} |" in md, f"step-options.md: add a row for '{label}'"


def test_chain_statuses_documented():
    md = _text("chains")
    for label in chains.STATUS_LABELS.values():
        assert f"| {label} |" in md, f"chains.md: add a row for '{label}'"
    tasks_md = _text("tasks")
    for status, label in chains.STATUS_LABELS.items():
        assert f"`{status}`" in tasks_md and label in tasks_md, f"tasks.md: run result {status}"


def test_permissions_documented():
    md = _text("admin")
    for p in models.PERMISSIONS:
        assert f"`{p}`" in md, f"admin.md: document the `{p}` permission"


def test_log_outcomes_documented():
    md = _text("activity")
    for outcome in ("pass", "no-match", "stop", "skip", "sent", "error"):
        assert f"| {outcome} |" in md, f"activity.md: add a row for the '{outcome}' outcome"
