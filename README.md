# xMender

AI-agent based everyday automation. For now: watch a Gmail inbox, run each new
email through user-defined **tasks** (filters and agent steps), and post
results to Discord.

- Python 3.11+ (developed on 3.14), FastAPI, SQLAlchemy + Alembic
- Web UI on `http://127.0.0.1:25879`
- Runs as a systemd service under a normal user

## Quick start

```bash
scripts/setup.sh                # creates .venv, installs deps, copies .env.example -> .env
.venv/bin/python -m xmender     # prints a temporary admin password on first start
```

Open `http://127.0.0.1:25879`, paste the temporary password and choose a new
one for the `admin` account. Until that is done a new temporary password is
printed on every start.

## Run as a service

```bash
sudo scripts/install-service.sh            # runs as the invoking user
sudo scripts/install-service.sh xmender    # or a dedicated user
journalctl -u xmender | grep 'Temporary password'
```

The unit (`deploy/xmender.service`) sets `User=`/`Group=`, never runs as
root, and is sandboxed so it can only write `data/`.

## Configuration

Copy `.env.example` to `.env` (it is git-ignored). Main keys:

| Key | Default | |
|---|---|---|
| `XMENDER_PORT` | `25879` | |
| `XMENDER_ALLOW_EXTERNAL_ACCESS` | `false` | `true` binds `0.0.0.0` instead of `127.0.0.1` |
| `XMENDER_DATA_DIR` | `./data` | database, secret key |
| `XMENDER_DATABASE_URL` | SQLite in data dir | any SQLAlchemy URL, e.g. PostgreSQL |
| `XMENDER_SECRET_KEY` | generated `data/secret.key` | encrypts stored credentials |
| `XMENDER_POLL_INTERVAL_MINUTES` | `5` | automatic IMAP check interval |
| `XMENDER_SECURE_COOKIES` | `false` | set `true` behind HTTPS |

If you enable external access, put xMender behind a reverse proxy with HTTPS
and turn on `XMENDER_SECURE_COOKIES`.

## Data

SQLite (WAL mode) in `data/` by default; switch to PostgreSQL with
`XMENDER_DATABASE_URL` (`pip install "psycopg[binary]"` first). The schema is
managed by Alembic and upgraded automatically on start, so restarts and code
updates keep all data. After changing models, create a migration:

```bash
.venv/bin/alembic revision --autogenerate -m "describe change"
```

Back up `data/` (database **and** `secret.key`: without the key, stored
passwords and API keys cannot be decrypted).

## Accounts

- `admin` is built in: it cannot be deleted or demoted and can do anything.
- Admins add/remove users, grant permissions (`integrations`, `tasks`), and can
  make other users admins (those remain deletable).
- Self-service account creation exists but is **off** by default
  (Admin → Registration).

## Integrations

All are tested before saving.

- **Gmail**: IMAP `imap.gmail.com:993` for reading (read-only, mail is never
  marked as read); optional SMTP `smtp.gmail.com:465` SSL for sending, which can
  be toggled later without losing settings. Needs an
  [App Password](https://myaccount.google.com/apppasswords). The test only
  logs in; no email is sent. Only mail arriving after the inbox is connected is
  processed.
- **Discord webhook**: verifying a webhook means posting to it, so the UI says
  exactly what will be sent and lets you skip the test. Old `discordapp.com` and
  versioned URLs are normalised to `discord.com/api/v10`; forum channels are
  supported via `?thread_id=` or an auto-created thread.
- **Anthropic API**: verified by listing models (no tokens spent). The model
  list in every picker comes live from the API.

## Tasks

A task belongs to one Gmail inbox and is an ordered chain of steps:

| Step | Does |
|---|---|
| Filter (Built-in) | Gmail-style From/To/Subject/has words/doesn't have/attachment. No match ends the chain. |
| Filter (Agent) | The LLM reviews the email against your instructions; passes only if the reply ends with `FILTER MATCH`. |
| Webhook (Agent) | The LLM writes a notification from your instructions; posted as an aqua embed titled `xMender Notification`. |

Agent steps use the step's model or your default model (Settings). Prompts
wrap the email and your instructions in per-call random tags, mark the email
as untrusted data, and give the model no tools. Webhook posts disable all
mentions.

## API usage

Settings shows Anthropic token usage and cost per model, task and day (today,
7 days, 30 days, this month, all time; admins can switch to all users). Cost
is computed from the token counts each API response reports and Anthropic's
list prices, kept in `xmender/services/pricing.py` with the date they were
checked. Costs are stored per call in nano-dollars, so small totals are exact
to the sixth decimal. Calls on a model without a known price are counted but
shown as "price unknown". Usage is recorded from this version on; earlier
calls are not included.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## License

MIT, see `LICENSE`. Fira Code font: SIL OFL 1.1 (`licenses/`).
