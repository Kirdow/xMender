# Step reference

Every step type, what it does, its settings and what it **outputs**. Outputs are the values a *named* step hands to later steps, used as `{{name.output}}` in [placeholders](#placeholders) and in [Run this step conditions](#step-options/run-this-step).

Every filter also outputs `matched` (`true` or `false`, after **Invert** is applied).

| Step | Group | Uses AI | Outputs |
|---|---|---|---|
| [Filter (Built-in)](#steps/filter_builtin) | Filter | No | `matched` |
| [Filter (Newsletter / bulk)](#steps/filter_bulk) | Filter | No | `matched`, `signals` |
| [Filter (Gmail category / label)](#steps/filter_gmail) | Filter | No | `matched`, `category`, `labels` |
| [Filter (Time window)](#steps/filter_time) | Filter | No | `matched`, `local_time` |
| [Filter (Sender history)](#steps/filter_sender) | Filter | No | `matched`, `seen_count` |
| [Filter (Phishing signals)](#steps/filter_phishing) | Filter | No | `matched`, `signals`, `count` |
| [Filter (Agent)](#steps/filter_agent) | Filter | Yes | `matched` |
| [Classify (Agent)](#steps/classify_agent) | Agent | Yes | `label`, `reason` |
| [Extract (Agent)](#steps/extract_agent) | Agent | Yes | one per field you define |
| [Webhook (Agent)](#steps/webhook_agent) | Action | Yes | none |
| [Template post (Discord)](#steps/template_post) | Action | No | none |
| [HTTP webhook](#steps/http_post) | Action | No | `status` |

## Filters {#filters}

A filter checks the email. When it matches, the task goes on to the next step (log outcome **pass**). When it does not, the task stops (outcome **stop**, run result `stopped`), unless the filter's options say **Continue**, in which case the outcome is **no-match** and later steps can check `matched`. See [Step options](#step-options).

### Filter (Built-in) {#filter_builtin}

Gmail-style criteria, no AI, free. Fill in only what you need; every filled field must match.

| Field | How it matches |
|---|---|
| From | The From header (name and address). Text anywhere in it, for example `billing@` or `shop.com`. |
| To | The To and Cc headers. |
| Subject | The subject. |
| Has the words | Every word must appear in the subject or body. Use `"quotes"` for a phrase: `order "has shipped"`. |
| Doesn't have | None of these words may appear in the subject or body. |
| Attachment | **Either** (ignore), **Has attachment** or **No attachment**. |

Matching is case-insensitive and finds text anywhere (`pay` also matches `payment`). In **From**, **To** and **Subject** you can list alternatives separated by `,` or ` OR ` (capital letters): `invoice OR receipt, bill`. Any one is enough.

**Attachment details** (shown unless *No attachment* is chosen). At least one attachment must match every detail you fill in; filling any detail means an attachment is required. Separate several values with `,`.

| Detail | Example | Meaning |
|---|---|---|
| File types | `pdf, docx` | File name extension. |
| File name | `invoice*, receipt-*.pdf` | Name pattern: `*` is any text, `?` one character. |
| Content type | `image/, application/pdf` | The attachment's type, matched from the start. |
| Min size / Max size (KB) | `50` | Size limits in kilobytes. |

**Use regular expressions**: each text field becomes one case-insensitive regular expression, searched anywhere in its text (use `|` for alternatives, `^` and `$` to anchor). *Has the words* must be found; *Doesn't have* must not be found. Each search is stopped after a quarter second; a pattern that is too slow makes the step fail with an error instead of hanging. Only the first 200,000 characters of subject and body are searched.

The run log says what decided it, for example `all criteria matched`, *subject did not match* or `missing words: invoice`.

### Filter (Newsletter / bulk) {#filter_bulk}

Spots mailing lists and automated mail from the email's headers. No AI, free. Matches when **any** checked sign is present.

| Sign | Checked headers |
|---|---|
| Newsletter or mailing list (List-Unsubscribe / List-Id) | `List-Unsubscribe` or `List-Id` is present. |
| Bulk or automated (Precedence, Auto-Submitted, Feedback-ID) | `Precedence: bulk/list/junk`, `Auto-Submitted` other than `no`, or a `Feedback-ID` header. |
| Sent from a no-reply address | The sender address starts with `noreply`, `no-reply`, `donotreply`, `do-not-reply`, `mailer-daemon` or `bounce`. |

Output `signals`: the signs that fired, as a comma list of `newsletter`, `bulk`, `noreply` (empty if none).

> [!tip]
> Tick **Invert** under Options to keep only personal mail: the filter then passes when *none* of the signs are present.

### Filter (Gmail category / label) {#filter_gmail}

Uses Gmail's own sorting. No AI, free.

| Field | Meaning |
|---|---|
| Inbox category | Gmail's inbox tabs: `primary`, `social`, `promotions`, `updates`, `forums`. Matches if the email is in any ticked one. Leave all unticked to ignore the category. |
| Labels | Comma list. Matches if the email has **any one** of them. Use the label name as Gmail shows it, including nested ones like `Work/Clients`. System labels work too: `important`, `starred`. Case does not matter. |

If both are set, the category must match **and** one of the labels must be present.

Labels added by your own Gmail filters count, because Gmail applies them when the mail arrives. If you turned inbox tabs off in Gmail, every email counts as `primary`.

Outputs:

- `category`: the Gmail category, like `promotions` (empty if unknown).
- `labels`: all the email's labels, comma separated, like `Important, Bills`.

The step fails with an error when the server does not offer Gmail's label information (only possible with non-Google IMAP servers), or when a category is required but Gmail did not report one.

### Filter (Time window) {#filter_time}

Matches mail **processed** during chosen days and hours. It uses the time xMender handles the email, not the email's Date header (the sender controls that). No AI, free.

| Field | Meaning |
|---|---|
| Days | The weekdays the window is open. |
| From / Until | Start and end time, 24-hour. Same start and end means the whole day. An end before the start runs past midnight and belongs to the day it started: Friday `22:00`–`02:00` includes Saturday 01:00. The end time itself is outside the window. |
| Time zone | The zone the times are in. Default: your time zone from [Settings](#account/time-zone), or UTC with a warning if none is set. |

Output `local_time`: the processing time as checked, like `Mon 09:30 Europe/Stockholm`.

> [!tip]
> Tick **Invert** for "outside these hours", for example to notify only after work.

### Filter (Sender history) {#filter_sender}

Matches on how often the sender has written to this inbox before. No AI, free.

| Match when | Meaning |
|---|---|
| First email from this sender | xMender has never processed mail from this address in this inbox. |
| Sender has written before | At least one earlier email from this address. |
| Sender writes often | At least **N** earlier emails, optionally only counting the last **D** days (1–3650). N is 1–1000. |

The history only covers mail xMender has processed for **this inbox**, so it starts when the inbox was connected. The sender is compared by address only (not the display name), ignoring case.

Output `seen_count`: how many earlier emails from this address xMender has (all time, up to 1000).

> [!tip]
> Invert **Sender writes often** to rate-limit a noisy sender: with N = 3 and D = 1, the filter stops the task once someone has written three times in a day.

### Filter (Phishing signals) {#filter_phishing}

Counts warning signs of phishing and matches when at least **Signs needed** of the ticked signs are present. No AI, free.

| Warning sign | What is checked |
|---|---|
| Gmail's SPF, DKIM or DMARC check failed | Gmail's own authentication result says `fail` (or SPF `softfail`). Only the header Gmail itself added is trusted; senders cannot fake it. |
| Reply-To goes to a different domain than From | Replies would go to another organisation than the sender. |
| Display name contains a different email address | For example `"support@paypal.com" <x@evil.example>`. |
| Mentions a protected name but comes from another domain | The sender name or subject contains one of your **Protected names**, but the sender's domain is not one of that name's domains. |
| Sent from a free email provider | Gmail, Outlook, Yahoo, iCloud, Proton and similar. |

**Signs needed**: how many of the ticked signs must be present, from 1 up to the number ticked.

**Protected names**: one per line, `Name = domain, domain`. Subdomains count (`mail.paypal.com` is fine for `paypal.com`).

```
PayPal = paypal.com
My Bank = mybank.se, mybank.com
```

Needed only for the *protected name* sign; that sign cannot be ticked without at least one line.

Outputs:

- `signals`: the signs that fired, as a comma list of `auth_fail`, `reply_to_mismatch`, `name_has_address`, `brand_mismatch`, `free_mail`.
- `count`: how many fired.

> [!note]
> Free email alone is normal for real people. Combine it with other signs, or set **Signs needed** to 2 or more.

### Filter (Agent) {#filter_agent}

An AI model reads the email and decides. Needs the Anthropic integration.

| Field | Meaning |
|---|---|
| Instructions | Required. Describe which emails should pass, for example *"Emails from a real person asking me something that needs a reply."* |
| Attachments | Optional. Let the model read PDF and image attachments. See [AI steps](#ai/attachments). |
| Model | The model to use; default is the one in [Settings](#account/default-model). |

The model explains its reasoning briefly and ends with `FILTER MATCH` or `NO MATCH`. The email passes only if the reply **ends with** `FILTER MATCH`. If the model declines to answer, the filter does not match. The full reply is shown in the run log.

## Agents {#agents}

Agent steps use AI to understand the email and output values for later steps. They need the [Anthropic integration](#integrations/anthropic) and cost tokens; see [AI steps](#ai).

### Classify (Agent) {#classify_agent}

Sorts the email into one of your categories.

| Field | Meaning |
|---|---|
| Categories | Up to 30, each with a name (up to 60 characters) and a description of what belongs there. Names must be unique, ignoring case. |
| Instructions | Optional extra guidance, for example *"Receipts for things I already paid are not invoices."* |
| Attachments, Model | As for every agent step. |

A category called `other` is always added automatically for "nothing else fits"; you cannot add your own `other`.

Outputs:

- `label`: the chosen category, spelled exactly as you wrote it, or `other`. If the model answers something that is not a category, the label becomes `other` and the log notes what it answered.
- `reason`: the model's one-line reason (up to 500 characters).

Use it to route mail: on later steps set **Run this step → Only if category… label equals invoice**. The value box suggests your category names.

### Extract (Agent) {#extract_agent}

Pulls values out of the email into fields you define, for example the amount and due date of a bill.

| Column | Meaning |
|---|---|
| Key | The output name: starts with a letter, then `a-z`, `0-9` or `_`, at most 32 characters. Used as `{{name.key}}`. `matched` is not allowed. |
| Type | What kind of value it is; see below. |
| What it is | A description for the model, for example *"Total amount to pay"*. Good descriptions give better results. |
| Required | If ticked and no value is found, the step fails with *Required field(s) not found*. |

Up to 20 fields. **Instructions** (optional) give extra guidance, like *"Amounts are in SEK."*

| Type | Becomes | Notes |
|---|---|---|
| Text | text | Up to 2000 characters. |
| Number | a number like `1234.5` | Currency signs and spaces are removed. A comma is treated as a thousands separator, so `1,234.50` is `1234.5`. |
| Whole number | a number like `3` | Values with decimals become empty. |
| Yes / no | `true` or `false` | `yes`/`no` also work. |
| Date | `YYYY-MM-DD` | Anything that is not a valid date becomes empty. |

Values the email does not contain are **empty**: in a template they print as nothing (use `| default:…`), and in a JSON body a lone placeholder becomes `null`. See [Placeholders → How values are inserted](#placeholders/values).

The values are checked and converted by xMender even when the model already follows the format, so later steps can rely on them. The log shows the values found, like `extracted 2 of 3 field(s)`.

> [!warning]
> Amounts written with a decimal comma (`12,50`) are read as `1250`. If your mail uses decimal commas, add to the instructions: *"Write numbers with a dot as the decimal separator."*

## Actions {#actions}

Actions send something out. Their log outcome is **sent**.

### Webhook (Agent) {#webhook_agent}

An AI model writes a Discord notification about the email, following your instructions.

| Field | Meaning |
|---|---|
| Discord webhook | Where to post. |
| Instructions | Required. What the message should say, for example *"Summarise in 2 bullet points and list any due dates."* |
| Embed title | **Default**: always `xMender Notification`. **Written by the model**: the model also writes a short title (up to about 80 characters) in the same call; if it forgets, the default is used and the log shows a warning. **Template**: a title [template](#placeholders) such as `{{email.subject}}`. |
| Attachments, Model | As for every agent step. |

The message is posted as an aqua embed, with `Subject: <email subject>` in the footer. The model keeps it under about 3500 characters; Discord's limit of 4096 is enforced by cutting.

The model is told not to copy links, contact details or calls to action from the email unless your instructions ask for them. If you want the link to an order page, say so.

### Template post (Discord) {#template_post}

Posts a Discord embed built from your own templates. No AI, free, predictable.

| Field | Meaning |
|---|---|
| Discord webhook | Where to post. |
| Title | Template, up to 500 characters. Empty means `xMender Notification`. Discord cuts titles at 256 characters. |
| Message | Required template, up to 4000 characters. Discord markdown works (`**bold**`, lists, links). |
| Footer | Optional template, up to 500 characters. |

All three fields accept [placeholders](#placeholders). The **Placeholders** list below the fields shows every value you can use; click one to insert it where the cursor was. Nobody is ever pinged. The log shows the message as it was sent.

### HTTP webhook {#http_post}

Sends a request to one of your [HTTP webhooks](#integrations/http-webhooks) with a body you write.

| Field | Meaning |
|---|---|
| HTTP webhook | Which one. The URL, method and headers come from the integration. |
| Body format | **JSON** (sent as `application/json`) or **Plain text** (sent as `text/plain`). |
| Body | Required template, up to 8000 characters. |

**JSON** bodies must be valid JSON. Placeholders go **inside strings**, where xMender escapes them so email text can never break the JSON. A string that is exactly one placeholder without modifiers keeps the value's own type:

```
{
  "subject": "{{email.subject}}",
  "amount": "{{bill.amount}}",
  "urgent": "{{bill.urgent}}",
  "note": "Due {{bill.due | default:unknown}}"
}
```

With `amount` 49.9 and `urgent` true this sends `"amount": 49.9, "urgent": true`, not text. A missing value sends `null`. See [Placeholders → JSON bodies](#placeholders/json).

**Plain text** bodies are the template with placeholders filled in, for example an ntfy message.

Output `status`: the HTTP status code the server answered, like `200`. Any answer outside 2xx is an error. The log shows the body that was sent.
