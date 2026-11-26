# Overview

xMender watches your Gmail inboxes and runs every new email through **tasks** you build yourself. A task is a short list of **steps**: filters that decide whether the email is interesting, AI agents that read, sort or pull data out of it, and actions that post the result to Discord or send it to any web service.

Nothing is sent from your mailbox and nothing in it is changed. xMender only reads new mail.

## The building blocks {#concepts}

| Thing | What it is |
|---|---|
| Integration | A connection to an outside service: a Gmail inbox, a Discord webhook, an HTTP webhook, or your Anthropic API key. Set up under **Integrations**. |
| Task | A named recipe that belongs to one Gmail inbox. Every new email in that inbox runs through each enabled task. |
| Step | One part of a task. Steps run top to bottom. There are three kinds: **filters** (aqua), **agents** (lime) and **actions** (pink). |
| Placeholder | A `{{name.field}}` marker inside a template that is replaced with a value from the email or an earlier step. |
| Run | One task applied to one email. Every run is listed on the **Dashboard** with what each step did. |
| Chain | A task set to run only after another task, depending on how that one ended. |

## Quick start {#quick-start}

1. **Connect a Gmail inbox** under **Integrations**. You need a Google App Password; see [Gmail](#integrations/gmail).
2. **Connect somewhere to send results**: a [Discord webhook](#integrations/discord) or an [HTTP webhook](#integrations/http-webhooks).
3. Optional: **add your Anthropic API key** if you want AI steps; see [Anthropic API](#integrations/anthropic). Then pick a **default model** under **Settings**.
4. **Create a task** under **Tasks**: pick the inbox, add a filter, then an action. See [Tasks](#tasks).
5. Wait for new mail, or press **Refresh now** on the Dashboard. Open an email there to see what every step did.

> [!note]
> Only mail that arrives **after** an inbox is connected is processed. Mail already in the inbox is never touched.

## A first task {#example}

"Post every invoice to my #bills channel":

1. **Filter (Built-in)**: Subject `invoice OR receipt`.
2. **Template post (Discord)**: pick your webhook, title `{{email.subject}}`, message `From {{email.from}}` and `{{email.snippet}}`.

A smarter version with AI:

1. **Classify (Agent)** named `category`, with categories `invoice` and `personal`.
2. **Extract (Agent)** named `bill`, with fields `amount` (number) and `due` (date). Under **Options → Run this step**, choose *Only if category… label equals invoice*.
3. **Template post (Discord)**, also only if `category` label equals `invoice`: message `Pay {{bill.amount}} by {{bill.due | default:unknown date}}`.

Read on in [Tasks](#tasks), the [Step reference](#steps) and [Placeholders and templates](#placeholders).

## Using these docs {#using-the-docs}

- Open the docs from **Docs** at the bottom of the sidebar. Click the arrow next to it to open them in a new browser tab instead.
- The **?** button on every step in the task editor and the **Open placeholder docs** button in each **Placeholders** list jump straight to the matching part.
- Use the search box to find any word across all pages. Press Enter to open the first result and Esc to clear the search.
