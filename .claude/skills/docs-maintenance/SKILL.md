---
name: docs-maintenance
description: Keeps xMender's user docs (xmender/web/static/docs/*.md, shown in the in-app Docs modal and at /docs) accurate. Use whenever a change alters anything a user can see or rely on - a step type, step setting or output, placeholder or modifier, condition, chain rule, integration, limit, default, error message, UI label, page or permission - and before committing such a change. Also use when asked to write, extend, restructure or check the docs.
---

# Keeping the user docs accurate

xMender's end-user documentation is part of the product. A change that makes
any sentence in it wrong is **not finished** until the docs are corrected in
the **same commit**. Treat a stale doc like a failing test.

## Where the docs live

```
xmender/web/static/docs/
  index.json        groups -> sections {id, title, file}; order = sidebar order
  <section>.md      one page each; first line must be "# <title from index.json>"
xmender/web/static/docs.js   renderer + search; used by BOTH the modal (app.js
                             openDocs) and the standalone /docs page (docs.html)
tests/test_docs.py           drift checks; run them
```

There is exactly one copy of the content. Never put documentation text into
`app.js` or `docs.html`; never fork content between the modal and the page.

## Which page covers what

| Code area | Doc page(s) |
|---|---|
| `services/steps/*`, `steps/__init__.py` (REGISTRY), `STEP_FORMS` / `STEP_OUTPUTS` in app.js | `steps.md` (per-step `{#type}` section and the summary table) |
| `services/pipeline.py` (name, when, on_error, negate, on_no_match, ops) | `step-options.md`, `tasks.md` (run results) |
| `services/template.py`, `templateHelp()`, http_post JSON rendering | `placeholders.md` |
| `services/chains.py`, `api/tasks.py` chain planning, chain UI | `chains.md`, `tasks.md` |
| `services/llm.py`, `prompts.py`, `steps/base.py` attachments | `ai.md` |
| `services/filters.py`, `signals.py`, `timewindow.py` | `steps.md` (the matching filter) |
| `services/gmail.py`, `poller.py` | `mail.md`, `integrations.md#gmail`, `activity.md` |
| `services/discord.py`, `http_hook.py`, `api/integrations.py` | `integrations.md` |
| `services/usage.py`, `pricing.py`, Usage page | `usage.md` |
| `api/auth.py`, `api/users.py`, `models.PERMISSIONS`, Settings/Admin pages | `account.md`, `admin.md` |
| masking, secrets, CSP, what is stored or sent | `privacy.md` |
| any new user-facing error text | `troubleshooting.md` (if users can act on it) |
| `config.Settings` defaults users notice (poll interval, batch size, session days) | `mail.md`, `account.md`, `activity.md` |

Operator-only topics (env vars, systemd, migrations, moving hosts) belong in
`README.md`, not in these docs.

## Workflow for a code change

1. Before editing code, `grep -rn` the docs for the feature's UI label, config
   key, limit or error text to find every sentence that describes it.
2. Make the code change.
3. Update every affected sentence, table row and example. Check numbers
   (limits, defaults), labels (must match the UI exactly) and behaviour.
4. New feature: document it where a user would look for it, add a
   troubleshooting entry for errors users can fix, and link related pages.
5. Run `.venv/bin/python -m pytest -q tests/test_docs.py` (and the full suite).
6. Commit docs together with the code.

Adding a step type additionally needs: a `### <label> {#<type>}` section in
`steps.md` listing settings and outputs, a row in the summary table at the top
of `steps.md`, and outputs in backticks. The editor's "?" button links to
`steps/<type>`, and the tests enforce all of this.

## What tests/test_docs.py enforces

- `index.json` and the `.md` files match; each file starts with its title.
- Every `[text](#section/anchor)` link, every `openDocs('…')` / `docsLink('…')`
  target in app.js, and `steps/<type>` for every step type resolves.
- Every step type has its section, heading text = `StepDef.label`, and every
  output appears in its section and the summary table.
- All bulk/phishing checkbox labels, signal keys and Gmail categories appear.
- Every `template.EMAIL_FIELDS` entry and `template.MODIFIERS` entry is in
  `placeholders.md`, and app.js `EMAIL_FIELDS` equals the backend list.
- Every condition label (app.js `COND_OPS`), chain status label, permission
  and run-log outcome has its row.

The tests catch names, not meaning. A changed limit, default or behaviour still
needs a human (you) to update the prose. Do not weaken a test to make it pass;
fix the docs.

## Writing style

- Write for end users of the web UI, not developers. Use the UI's own words
  (button and field labels in **bold**, exactly as shown).
- Short sentences, concrete examples, tables for settings. Say what happens,
  including limits and failure cases. Never document behaviour you have not
  verified in the code.
- Use they/them or "you"; no emojis.

## Markdown subset (docs.js)

Only this renders; anything else shows as plain text.

- `#`, `##`, `###`, `####` headings. Ids are slugs of the text
  (`[^a-z0-9]+` -> `-`); give a stable id with `## Title {#my-id}`. Ids must be
  unique within a page. `##` and `###` appear in the sidebar and in search.
- Paragraphs; `-` and `1.` lists (indent 2 spaces to nest or continue an item).
- ```` ``` ```` fenced code blocks (no language highlighting).
- Tables with a header row and `|---|` separator. Write `\|` for a literal
  pipe inside a cell (for example `{{x.y \| clip:20}}`).
- `> ` callouts; first line `[!tip]` (lime), `[!warning]` (pink) or `[!note]`
  (aqua, default).
- Inline: `` `code` `` (single backticks only, no nesting), `**bold**`,
  `*italic*`, `[external](https://…)` (opens a new tab) and doc links
  `[text](#section)` or `[text](#section/heading-id)`.

Extending the renderer: change `docs.js` only (both views use it), keep all DOM
built with `textContent` (no `innerHTML`; CSP is `script-src 'self'`), update
this list, and mirror any slug change in `slug()` in `tests/test_docs.py`.
