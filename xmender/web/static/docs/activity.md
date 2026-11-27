# Dashboard and run log

The **Dashboard** shows your inboxes and what your tasks did with recent mail. It only shows your own inboxes and mail.

## Inboxes {#inboxes}

One card per connected Gmail inbox, with chips:

| Chip | Meaning |
|---|---|
| checked … | When the inbox was last checked. |
| every N min | How often xMender checks. |
| N queued | More new mail is waiting than one check handles; it follows on the next checks. |
| ok / error | Whether the last check worked. On error the message is shown below. |

**Refresh now** checks all your inboxes right away and reports how many new emails were processed, or the error. See [How mail is checked](#mail).

## Live updates {#live}

While the Dashboard is open, it reloads the inbox cards and Recent activity every 30 seconds. The line next to **Refresh now** counts down to the next update. This only shows what xMender already has; it does not check your mail any sooner. New mail still arrives at the regular check (`every N min`) or when you press **Refresh now**.

Updates never get in your way:

- Open run logs, opened email text, scroll positions and keyboard focus stay as they are. A card whose tasks finish in the meantime is updated in place.
- Mail that arrives above where you are reading does not push the page; what you are looking at stays put.
- A card with selected text is left alone until the selection is cleared.
- An email you have open stays in the list even after newer mail pushes it past the 50 shown.

If an update fails, the line says so and retries 30 seconds later.

### New mail marks {#new-mail}

Mail that appears while the page is open gets a red edge and a `new` badge, and a red **new above** bar separates it from what was there before. The browser tab title shows the count, for example `(2) xMender`, so you can see it from another tab.

The marks clear by themselves once you are looking: after the page has had focus for about 12 seconds in a row, plus 5 more. If the page already has your focus when mail arrives, its marks stay for 5 seconds so you still notice it. Switching to another window or tab restarts the count.

## Recent activity {#recent-activity}

The 50 most recent emails xMender processed, newest first, kept up to date while the page is open (see [Live updates](#activity/live)). Each card shows the subject, when it was processed, the sender and one chip per task that ran: `Task name: result`.

- **Click a card** to open the run log of every task for that email.
- The **arrow** button shows the start of the email's text.
- *No task ran on this email* means no enabled task existed for that inbox when the email arrived.

Deleted tasks keep their runs here under the name they had.

## Reading a run log {#run-log}

Each task's run starts with its name and result chip (`completed`, `partial`, `stopped`, `error`, `skipped`; see [Tasks → Run results](#tasks/run-status)). Below it, one line per step:

```
2.  Classify (Agent)  pass  label: invoice · claude-… · 1,240 in / 85 out · $0.004120
```

From left to right: the step number (`↳` for the chain line of a [chained task](#chains/running)), the step type, the **outcome**, and details.

| Outcome | Meaning |
|---|---|
| pass | A filter matched, or an agent step finished. |
| no-match | A filter did not match, and was set to continue. |
| stop | A filter did not match and ended the task. |
| skip | The step's **Run this step** condition did not hold (or, on the `↳` line, the chain condition). |
| sent | An action posted or sent its message. |
| error | The step failed; the detail says why. |

The details can include:

- what decided a filter, for example `missing words: invoice` or `3 sign(s): auth_fail, reply_to_mismatch, free_mail`;
- the model that answered, the attachments it read, tokens and cost;
- a **warning**, for example `bill.due had no value`, `no time zone set in Settings; used UTC`, or skipped attachments.

A box under the line shows the full output: the AI's reply, the values Extract found, the Discord message as sent, or the HTTP body as sent (cut after 4,000 characters).

> [!tip]
> When a task does not do what you expect, open the email here first. The run log shows exactly which step stopped it and why.
