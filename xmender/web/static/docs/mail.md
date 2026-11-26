# How mail is checked

## Polling {#polling}

xMender checks every connected inbox on a fixed schedule: right when the server starts, then every few minutes (5 by default; the server owner sets it). The Dashboard shows the interval on each inbox card, for example `every 5 min`.

**Refresh now** on the Dashboard checks all your inboxes immediately and tells you how many new emails were processed. If a check is already running for an inbox, the new one waits for it to finish.

## Only new mail {#only-new-mail}

When you connect an inbox, xMender remembers where the inbox is "now" and only processes mail that arrives after that. Old mail is never run through tasks.

If Google resets the inbox's internal numbering (rare), xMender starts again from "now" without processing anything, to avoid running old mail twice.

## Batches {#batches}

Each check processes at most a set number of emails (25 by default). If more arrived, the inbox card shows a pink **queued** chip and the rest are handled on the next checks.

Every email is processed once. Checking again, or a restart of the server, never runs tasks on the same email twice.

## What happens to each email {#per-email}

1. The email is read without marking it as read. Gmail's own **category** (Primary, Promotions, …) and **labels** are fetched with it.
2. The email is saved in xMender's activity list.
3. Every **enabled** task of that inbox runs on it. Tasks that run after another task wait for that task first (see [Task chains](#chains)). Tasks marked **needs fixing** are skipped.
4. Each task's result is saved as a **run** that you can open on the Dashboard.

What xMender reads from each email: sender, recipients (To, Cc), subject, date, the text body (HTML mail is converted to text), attachments, all headers, and the Gmail category and labels.

## When a check fails {#errors}

If xMender cannot log in or read the inbox, the inbox card on the Dashboard turns red with the error, and the Integrations card shows **poll error**. Common causes:

- The App Password was deleted, or you changed your Google password (which revokes App Passwords). Create a new App Password and paste it under **Integrations → Edit**.
- A network problem between the xMender server and Google. These usually clear by themselves.

The next successful check clears the error. See [Troubleshooting](#troubleshooting) for more.
