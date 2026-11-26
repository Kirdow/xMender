# Placeholders and templates

Some fields are **templates**: text with placeholders that are filled in for each email. These are:

- [Template post (Discord)](#steps/template_post): Title, Message and Footer.
- [HTTP webhook](#steps/http_post): Body.
- [Webhook (Agent)](#steps/webhook_agent): Title template, when **Embed title** is set to *Template*.

AI **instructions** are not templates: the model already sees the whole email, and placeholders there are passed on as plain text.

## Writing a placeholder {#syntax}

A placeholder is two curly braces around a **source** and a **field**, separated by a dot:

```
{{email.subject}}
{{extract.amount}}
```

- The source is `email` (the email being processed) or the **name of an earlier step** (see [Step options → Name](#step-options/name)).
- Spaces inside the braces are allowed: `{{ email.subject }}`.
- Upper and lower case do not matter.
- Everything outside the braces is copied as written.

The **Placeholders** list under each template shows every placeholder you can use at that point. Click a field first, then click a placeholder to insert it at the cursor.

## Email fields {#email-fields}

| Placeholder | Value |
|---|---|
| `{{email.from}}` | The full sender, like `Jane Doe <jane@example.com>`. |
| `{{email.from_name}}` | Just the sender's name: `Jane Doe`. Empty if the sender has no name. |
| `{{email.from_addr}}` | Just the address, in lowercase: `jane@example.com`. |
| `{{email.to}}` | The To header. |
| `{{email.cc}}` | The Cc header (often empty). |
| `{{email.subject}}` | The subject. |
| `{{email.date}}` | The Date header as `2026-11-26T14:05:00+01:00`. Empty if missing. |
| `{{email.snippet}}` | The start of the body on one line, up to 300 characters. |
| `{{email.body}}` | The whole text body (HTML mail converted to text). Can be long: use `clip`. |
| `{{email.attachments}}` | Attachment names, comma separated. |
| `{{email.attachment_count}}` | The number of attachments. |
| `{{email.category}}` | Gmail's category, like `primary` or `promotions`. |
| `{{email.labels}}` | Gmail labels, comma separated. |

## Step outputs {#step-outputs}

A **named** step earlier in the task hands its outputs on: `{{name.output}}`. What each step type outputs is in the [Step reference](#steps). Examples:

| Placeholder | From | Value |
|---|---|---|
| `{{category.label}}` | Classify (Agent) named `category` | `invoice` |
| `{{category.reason}}` | the same | `Asks for payment of order 1234.` |
| `{{bill.amount}}` | Extract (Agent) named `bill` with a field `amount` | `49.9` |
| `{{phishing.signals}}` | Filter (Phishing signals) named `phishing` | `auth_fail, free_mail` |
| `{{hours.local_time}}` | Filter (Time window) named `hours` | `Fri 18:02 Europe/Stockholm` |
| `{{bulk.matched}}` | any filter | `true` or `false` |
| `{{http.status}}` | HTTP webhook named `http` | `200` |

Only steps **above** the template's step can be used, and only if they have a name. A [chained task](#chains) can also use the named steps of the tasks it runs after.

## Modifiers {#modifiers}

Add modifiers after a `|` to change the value. Several can be chained; they apply left to right.

| Modifier | Example | Result |
|---|---|---|
| `clip:N` | `{{email.body \| clip:500}}` | At most N characters; a cut value ends with `…`. N must be a positive whole number. |
| `default:text` | `{{bill.due \| default:no due date}}` | Uses the text when the value is empty. The text may contain spaces. |
| `oneline` | `{{email.body \| oneline}}` | Turns all line breaks and runs of spaces into single spaces. |
| `upper` | `{{category.label \| upper}}` | UPPERCASE. |
| `lower` | `{{email.subject \| lower}}` | lowercase. |

Chained: `{{email.body | oneline | clip:200}}` first joins the lines, then cuts to 200 characters. `{{bill.due | default:none | upper}}` gives `NONE` when there is no due date.

Modifier text is plain text: a placeholder inside a modifier, like `default:{{email.from_addr}}`, is not filled in.

## How values are inserted {#values}

- Values are inserted as **plain text**. Text from an email can never add placeholders, change your template or ping anyone in Discord.
- Yes/no values print as `true` and `false`; lists print comma separated; numbers print as they are.
- An output that exists but has no value (for example an extracted field the email did not contain) prints as **nothing**. Use `default:`.
- An output that is **missing** at run time, because the step it comes from was skipped or failed, also prints as nothing, and the run log shows a warning like `bill.amount had no value`.

## Types in JSON bodies {#json}

In an HTTP webhook with **Body format: JSON**:

- Placeholders only work **inside JSON strings**: `"subject": "{{email.subject}}"`. Without the quotes the body is not valid JSON and cannot be saved.
- Values are escaped, so quotes and line breaks in an email can never break the JSON.
- **Keeping types:** a string that is *exactly one placeholder*, without modifiers and without other text, is replaced by the value with its own type. `"{{bill.amount}}"` becomes `49.9`, `"{{bill.paid}}"` becomes `true`, `"{{email.attachment_count}}"` becomes `2`. Text values stay strings.
- A lone placeholder with no value becomes `null`.
- As soon as the string has other text or a modifier, the result is always text: `"{{bill.amount}} SEK"` gives `"49.9 SEK"`.

In **Plain text** bodies, Discord templates and titles, everything is text.

## When a template is checked {#checks}

On **Save task**, every template is checked. Saving is refused with a message when:

- a placeholder is not `{{source.field}}`, for example `{{subject}}` (missing `email.`);
- `email` has no such field;
- the source is not a named step **above** this one (or in a task this one runs after);
- that step has no such output (common with Extract: the key must match a field exactly);
- a modifier is unknown, or `clip` has no positive number;
- a template is longer than its limit.

## Examples {#examples}

Discord message for an invoice found by Extract (named `bill`):

```
**{{bill.vendor | default:Unknown sender}}** wants **{{bill.amount}} {{bill.currency | upper}}**
Due: {{bill.due | default:not stated}}

{{email.snippet}}
```

ntfy notification as a plain-text HTTP body:

```
{{email.from_name | default:Someone}}: {{email.subject | clip:120}}
{{email.snippet}}
```

JSON for Home Assistant or n8n:

```
{
  "title": "{{email.subject | clip:100}}",
  "from": "{{email.from_addr}}",
  "category": "{{category.label}}",
  "amount": "{{bill.amount}}",
  "attachments": "{{email.attachment_count}}"
}
```
