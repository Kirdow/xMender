# xMender

AI-agent based everyday automation. For now: watch a Gmail inbox, run each new
email through user-defined **tasks** (filters, agent steps and actions), and
post results to Discord or any HTTP endpoint.

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
| `XMENDER_HTTP_ALLOW_PRIVATE` | `false` | let HTTP webhooks call loopback/LAN addresses |

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

A task belongs to one Gmail inbox and is an ordered chain of steps.

**Filters** (a non-match ends the chain unless the filter is set to continue):

| Step | Matches |
|---|---|
| Filter (Built-in) | Gmail-style From/To/Subject/has words/doesn't have, optional regex mode, attachment type/name/size. |
| Filter (Newsletter / bulk) | Mailing lists (List-Unsubscribe/List-Id), bulk or automated mail, no-reply senders. |
| Filter (Gmail category / label) | Gmail's inbox tab (Primary, Promotions, ...) and/or labels, including ones your Gmail filters set. |
| Filter (Time window) | Mail processed on chosen days between two times, in your time zone (Settings). |
| Filter (Sender history) | First mail from a sender, a known sender, or one writing at least N times in D days. |
| Filter (Phishing signals) | Failed SPF/DKIM/DMARC (Gmail's verdict), Reply-To mismatch, address in display name, imitated names, free mail. |
| Filter (Agent) | The LLM reviews the email against your instructions; passes only if the reply ends with `FILTER MATCH`. |

**Agents:**

| Step | Does |
|---|---|
| Classify (Agent) | Puts the email into one of your categories (or `other`). |
| Extract (Agent) | Pulls typed fields (text, number, date, yes/no) out of the email. |

**Actions:**

| Step | Does |
|---|---|
| Webhook (Agent) | The LLM writes a notification from your instructions; posted as an aqua embed. The title is `xMender Notification` by default, or written by the model, or a template. |
| Template post (Discord) | Posts a Discord embed filled from a template; no LLM. |
| HTTP webhook | Sends a JSON or text body to an HTTP integration (ntfy, Slack, Home Assistant, ...). |

Every step can have a **name**, so later steps can use its result in
templates (`{{category.label}}`, `{{extract.amount}}`, `{{email.subject}}`)
and in **run-if conditions** ("only if `category` label equals invoice"),
which is how a task branches. Steps can also continue on error.

Agent steps use the step's model or your default model (Settings) and can
optionally read the email's PDF and image attachments. Prompts wrap the email
and your instructions in per-call random tags, mark the email (and its
attachments) as untrusted data, and give the model no tools. Posts disable
all mentions. HTTP webhooks cannot reach this machine or the local network
unless `XMENDER_HTTP_ALLOW_PRIVATE` is on.

## API usage

The Usage page shows Anthropic token usage and cost per model, task and day
(today, 7 days, 30 days, this month, all time; admins can switch to all users).
Cost is computed from the token counts each API response reports and Anthropic's
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
