# AGENTS.md

Guidance for coding agents working on xMender: an AI-agent based everyday
automation service. Today it watches Gmail inboxes over IMAP, runs each new
email through user-defined **tasks** (filters + LLM agent steps), and posts
results to Discord webhooks. Users reach it through a browser UI.

## Commands

```bash
scripts/setup.sh                                   # create .venv, install deps, copy .env.example -> .env
.venv/bin/pip install -r requirements-dev.txt      # adds pytest
.venv/bin/python -m pytest -q                      # full suite (~1 s)
.venv/bin/python -m pytest tests/test_services.py::test_validate_steps -q   # single test
.venv/bin/python -m xmender                        # run (127.0.0.1:25879 by default)
node --check xmender/web/static/app.js             # only "lint" for the frontend
XMENDER_DATA_DIR=<scratch> .venv/bin/alembic revision --autogenerate -m "describe change"
```

- No formatter or linter is configured. Match the surrounding style.
- Tests in `tests/test_api.py` share one session-scoped app, database and
  logged-in admin client. They depend on running in file order: for example
  `test_poller_processes_new_mail` needs the integrations created by
  `test_integrations_and_tasks`. Running a single test there can fail for
  that reason alone.
- **Never run against the real `./data` or port 25879.** The user runs a live
  instance from this directory with real credentials in `data/` and `.env`.
  For manual runs, set `XMENDER_DATA_DIR` to a scratch directory and
  `XMENDER_PORT` to something like 25899. `tests/conftest.py` already points
  tests at a temp dir.

## Architecture

```
xmender/
  __main__.py     entry: umask 077, logging, uvicorn
  app.py          FastAPI factory: lifespan (migrations -> admin bootstrap -> poller), CSRF/security-header middleware, static mount
  config.py       Settings from env + .env (cached)
  db.py           engine (SQLite WAL pragmas), session_scope(), get_db dependency, run_migrations()
  models.py       ORM models, PERMISSIONS, as_utc()
  security.py     argon2 hashing, session tokens, Fernet encrypt()/decrypt()
  bootstrap.py    built-in `admin` account + temp password on stdout
  api/            one router per area: auth, users (admin), integrations, tasks, dashboard
  services/       blocking domain logic: gmail, discord, llm, prompts, filters, pipeline, accounts, poller
  web/static/     index.html, app.js, style.css, fonts, icon.svg (no build step)
migrations/       Alembic (render_as_batch=True so ALTERs work on SQLite)
deploy/           systemd unit template; scripts/install-service.sh fills @USER@/@GROUP@/@DIR@
```

### Request flow
- Unsafe `/api/*` requests (POST/PUT/PATCH/DELETE) must send the header
  `x-xmender: 1`. The middleware returns 403 otherwise. The frontend `api()`
  helper and the test client already send it.
- Auth uses a `xmender_session` cookie (HttpOnly, SameSite=Strict). The
  database stores only a SHA-256 of the token (`AuthSession`).
- Use these dependencies from `api/deps.py`:
  - `current_user`: blocks while `must_change_password` is set.
  - `admin_user`.
  - `require("integrations" | "tasks")`: admins pass automatically.
- `get_db` commits at the end of the request and rolls back on exception, so
  an `HTTPException` raised after a mutation undoes it.

### Users
- `User.is_root` marks the built-in `admin`. It cannot be deleted or demoted,
  and only root may modify root.
- `is_admin` gives other users admin rights; they stay deletable.
- New permissions go in `models.PERMISSIONS`. The admin UI renders that list
  automatically.
- Self-registration is the `registration_enabled` key in `AppSetting`
  (default `False`), read and written through `get_app_setting` /
  `set_app_setting`.

### Integrations
All live in the `Integration` table, keyed by `kind` (`gmail` | `discord` |
`anthropic`):
- `config` (JSON): non-secret settings.
- `secret`: Fernet ciphertext.
- `state` (JSON): runtime data. For Gmail this is the IMAP cursor
  `uidvalidity`/`last_uid`, `last_polled_at`, `last_error` and `pending`.

Rules:
- Each user has at most one `anthropic` row; `gmail` and `discord` can have
  several.
- Every save runs a live check first. Gmail does an IMAP login, plus SMTP if
  sending is on; nothing is sent. Anthropic lists models, which costs nothing.
  Discord posts a real test message, so the user must choose
  `test: "send" | "skip"`.
- Gmail and Discord **Name** fields are labels inside xMender only. The
  Discord name is deliberately *not* sent as the webhook `username`; messages
  use the webhook's own Discord name and avatar. Gmail **Display Name** is
  reserved for a future From header. SMTP is currently only login-tested: no
  feature sends email yet.
- Secrets never leave the API: responses carry hints only (`key_hint`,
  `url_hint`). On edit, a blank secret field means "keep the stored one".
- An integration referenced by a task cannot be deleted (409).

### Mail processing (`services/poller.py`)
- `Poller._loop` polls every Gmail integration every
  `XMENDER_POLL_INTERVAL_MINUTES`, starting immediately at startup.
  `POST /api/poll` triggers the same thing for one user. A per-integration
  `asyncio.Lock` prevents overlapping polls.
- `poll_integration()` is blocking and runs through `asyncio.to_thread`:
  1. `gmail.fetch_new` opens INBOX read-only with `BODY.PEEK[]`, so mail is
     never marked as read.
  2. A missing cursor or a changed UIDVALIDITY resets the cursor to "now"
     without processing, so only mail arriving after connect is handled.
  3. At most `XMENDER_POLL_BATCH_SIZE` messages are processed per poll.
  4. Each message is parsed and stored as an `Email`; the unique key
     `(integration_id, uidvalidity, uid)` makes re-fetches harmless.
  5. The cursor advances per message.
  6. Each enabled task for that inbox runs and writes a `TaskRun`.
- Keep network calls (LLM, Discord, IMAP) **outside** DB transactions. The
  pattern: read what you need in one `session_scope()`, do the slow I/O, then
  write in a new `session_scope()`.

### Tasks and steps (`services/pipeline.py`)
A `Task` belongs to one Gmail integration and stores `steps` as JSON:
`[{"type": ..., "config": {...}}]`.

| type | behaviour |
|---|---|
| `filter_builtin` | `services/filters.py`, Gmail-like fields; no match stops the chain |
| `filter_agent` | LLM verdict; passes only if the reply ends with exactly `FILTER MATCH` |
| `webhook_agent` | LLM writes the text; posted as an embed titled `xMender Notification`, colour `0x00FFFF` |

To add a step type, touch all of these:
- `STEP_TYPES`
- `validate_steps()`: normalise and validate the config; it runs at save time
  with the live model list when available.
- `run_task()`
- a prompt builder in `services/prompts.py` if it uses the LLM
- in `app.js`: `STEP_DEFAULTS`, the `stepForm()` branch, and the chip colour
  map in `viewTasks`
- the step border colour in `style.css` (`.step[data-type=...]`)

Each step appends a log entry to `TaskRun.log` with these fields: `step`,
`type`, `label`, `outcome` (`pass` | `stop` | `sent` | `error`), `detail`,
and optionally `model`, `response` (clipped) and `warning`. The dashboard
renders these entries as-is.

### LLM (`services/llm.py`)
- Uses the official `anthropic` SDK (v2.x, built on `httpx2`). Always pass
  `api_key=` explicitly so host environment credentials are never used.
- Model choices must come from `list_models()` (Models API, cached 10 min per
  key). Never hard-code selectable models. `complete()` refuses models the
  key cannot see.
- A step without its own model falls back to `User.default_model`.
- For the models in `_FALLBACK_MODELS`, `complete()` sends
  `betas=["server-side-fallback-2026-07-01"], fallbacks="default"`. It retries
  without the fallback if the API rejects that parameter.
- A `stop_reason == "refusal"` result stops a filter and errors a webhook
  step.
- No `thinking` or `temperature` parameters are sent, because users can pick
  any model (and newer models reject explicit settings).
  `max_tokens = min(16000, model.max_tokens)`.
- Before changing Claude API usage, load the `claude-api` skill. SDK
  signatures, model IDs and parameters drift; verify rather than recall.

### Prompt-injection hardening (`services/prompts.py`)
- Untrusted email text and the operator's instructions are each wrapped in
  tags carrying a per-call random nonce (`<email_{nonce}>`,
  `<user_instructions_{nonce}>`). The nonce is stripped from the content.
- `_security_rules()` states which block is instructions and which is data,
  and that the model has no tools. Reuse it for any new agent step.
- The email body is capped at `BODY_CHAR_LIMIT`, with an explicit
  truncation note.
- Discord posts always send `allowed_mentions: {"parse": []}`.

### Discord (`services/discord.py`)
- `parse_webhook_url` accepts legacy hosts (`discordapp.com`, `canary`,
  `ptb`) and `/api/vNN` paths, and normalises to
  `https://discord.com/api/v10/webhooks/{id}/{token}`. An optional
  `?thread_id=` is kept.
- `send_embed` sends with `?wait=true` and handles 429 `retry_after`. On
  Discord error 220001 (forum channel) it retries with `thread_name`.
- On a 400 it flattens Discord's nested `errors` object into readable
  `field.path: message` text.
- Do not switch to Components V2 (`IS_COMPONENTS_V2` /
  `?with_components=true`): those messages cannot contain embeds.

### Data and schema
- The default database is SQLite at `data/xmender.db` (WAL). Any SQLAlchemy
  URL works via `XMENDER_DATABASE_URL` (PostgreSQL needs `psycopg`).
- `run_migrations()` runs Alembic `upgrade head` on every start.
- **Any model change needs a migration.** Autogenerate against a scratch
  `XMENDER_DATA_DIR`, review it, and commit it. Never `create_all`.
- SQLite returns naive datetimes. Everything is stored as UTC, so wrap reads
  in `as_utc()` before comparing.
- JSON columns are not mutation-tracked. Reassign the whole value
  (`integ.config = {**integ.config, "k": v}`) instead of mutating in place.
- The encryption key comes from `XMENDER_SECRET_KEY`, or else
  `data/secret.key` (created on first use, mode 0600). Losing it makes stored
  secrets unreadable.
- To migrate to another host: stop the service, then copy `data/` and `.env`.

## Coding patterns

### Python
- Python 3.11+ (developed on 3.14). Every module starts with
  `from __future__ import annotations` and a module docstring.
- Use type hints throughout, 4-space indent, lines up to about 100 columns.
- Services are blocking, synchronous code. Async API handlers call them with
  `await asyncio.to_thread(...)`.
- Services raise a user-presentable domain error (`GmailError`,
  `DiscordError`, `LLMError`, `StepConfigError`). Routers turn it into
  `HTTPException(400, str(e))`. Error text is shown directly in the UI, so
  write it for end users.
- Request bodies are Pydantic models defined next to their router. Responses
  are plain dicts built by `_x_dict()` helpers.
- Call services through the module (`gmail.test_imap(...)`), not via
  `from ... import func`, so tests can `monkeypatch.setattr(gmail, "test_imap", ...)`.
- Logging: `httpx`/`httpx2` are set to WARNING because request URLs contain
  webhook tokens. Never log secrets or webhook URLs.

### Frontend (`xmender/web/static/`)
- Vanilla JS in a single `app.js` with hash routing (`ROUTES`). There is no
  framework and no bundler.
- Build DOM only with `h(tag, attrs, ...children)`, which uses
  `textContent`. Never use `innerHTML` with server data.
- CSP is `script-src 'self'; style-src 'self'`. That means no inline
  `<script>`, no inline `style="..."` attributes and no `on*=` HTML
  attributes. Use CSS classes, and attach handlers through `h()`'s `onclick`
  etc.
- Reuse the existing UI helpers: `api()`, `toast()`, `withBusy()`, `modal()`,
  `confirmDialog()`, `field()`, `switchEl()`, `page()`, `modelSelect()`.
- Look and feel follows **Odysseus** (the user may have a slightly modified
  local checkout to use as reference; ask where): dark panels, a 240px sidebar shell, the Fira Code font
  (self-hosted, OFL licence in `licenses/`), rounded 12px cards and a gradient
  wordmark.
- Palette tokens are in `:root` in `style.css`:
  - `--primary` #00f0ff, bright aqua
  - `--secondary` #a6ff00, bright lime
  - `--ternary` #e83cff, bright pink-purple
  - `--danger`
  Use the tokens, never hex literals in rules.
- To preview logged-in views without real auth, start a scratch server whose
  app sets `dependency_overrides[deps.optional_user]` to return a seeded
  user, then take screenshots with
  `google-chrome-stable --headless=new --screenshot=... --virtual-time-budget=4000 "http://127.0.0.1:<port>/#/<route>"`.
  Keep such helper scripts in the scratchpad, not the repo.

### Config
- New settings go in `config.Settings` / `get_settings()`, using the
  `XMENDER_` prefix. Document them in `.env.example` (commented out if
  optional) and in the README table.
- `.env` is git-ignored. The real environment overrides `.env`.

## Git conventions
- Commit subject: `<type>: <message>`, at most 42 characters. Types are
  `add`, `remove`, `fix`, `chore`, `ci`, `docs`.
- Longer bodies go on line 3 onward, in the same `type: message` form.
- No emojis.
- End every commit with exactly
  `Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>` (adjust the model
  name and version to the agent actually used). The user stays the author;
  never set the agent as author or committer.
- Work happens on `master`; the remote `origin` is
  `git@github.com:Kirdow/xMender.git`.

## Agent access and permissions

Has access to, and may do:
- Read and write everything in this repository. Create and run the `.venv`.
  Run tests.
- Run the app locally on a scratch data dir and port.
- Make local commits, following the conventions above.
- Read the user's local Odysseus checkout, if any, as a style reference
  (read-only; do not modify it).
- Search the web and fetch docs, for example Discord API docs and Anthropic
  docs via the `claude-api` skill.
- Use headless Chrome (`google-chrome-stable`) and Firefox for screenshots.
  Node is available for `node --check`.

Does not have access to, or must not do without asking:
- **No real credentials.** There is no Gmail account or app password, no
  Discord webhook and no Anthropic API key. IMAP, SMTP, Discord and Anthropic
  behaviour is verified only through mocks. Real-world failures (like the
  Discord username rejection) surface only when the user tests, so ask the
  user to try it and paste the exact error.
- **No sudo.** Installing or restarting the systemd unit
  (`scripts/install-service.sh`, `systemctl`) is the user's job. The user's
  global rules require one batched `sudo -A bash -c '...'` and halting with
  instructions to run `askpass-manager set` if sudo itself fails.
- **The user's live instance is off limits:** `./data`, `.env`, and the
  service on port 25879. Don't read secrets from them, don't modify them and
  don't restart the service. Ask the user to restart after changes.
- Pushing to `origin`, opening PRs, or rewriting history are not
  pre-authorised. Ask first.
- No access to the user's browser session. UI checks use headless
  screenshots only.
