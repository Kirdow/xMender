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

## Recent activity {#recent-activity}

The 50 most recent emails xMender processed, newest first. Each card shows the subject, when it was processed, the sender and one chip per task that ran: `Task name: result`.

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
