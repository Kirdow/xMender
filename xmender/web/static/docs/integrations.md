# Integrations

Integrations connect xMender to other services. Open **Integrations** in the sidebar. Everything you connect is yours only; other users of the same server cannot see or use it.

**Every integration is tested before it is saved.** If the test fails, nothing is saved and the error tells you what went wrong.

Passwords, keys and webhook URLs are stored encrypted and are never shown again. When you edit an integration, leaving a secret field empty keeps the stored value.

## Anthropic API {#anthropic}

Needed for every **agent** step (anything with "(Agent)" in its name). Filters, Template post and HTTP webhook work without it.

1. Create a key at [platform.claude.com](https://platform.claude.com/settings/keys).
2. Click **Connect** (or **Replace key**) and paste it.

Saving checks the key by listing the models it can use. That costs nothing. You can have one key; replacing it swaps the key for all your tasks.

Afterwards, pick a **default model** under [Settings](#account/default-model). The key is shown masked (`sk-ant-••••`); hold the eye button to see the last characters.

> [!note]
> AI calls are billed by Anthropic to the account that owns the key. The [Usage](#usage) page estimates what your tasks have spent.

## Gmail {#gmail}

xMender reads a Gmail inbox over IMAP with a Google **App Password**. You can connect several inboxes.

1. Turn on **2-Step Verification** for your Google account (App Passwords need it).
2. Click **Open App Passwords** in the Connect Gmail dialog and create a password named for example "xMender". Google shows 16 letters in four groups; spaces do not matter.
3. Fill in the dialog and click **Test & save**. **Test only** checks the details without saving.

| Field | Meaning |
|---|---|
| Name | A label inside xMender, for example "Personal". |
| Gmail address | Your plain `@gmail.com` (or `@googlemail.com`) address, without a `+tag`. Each address can be connected once. |
| Display name | Reserved for sending mail in a future version. |
| App password | The App Password, not your Google password. |
| Enable sending (SMTP) | Optional. Checks that sending would work; no feature sends mail yet. It can be turned on and off later from the card. |
| Server settings | IMAP and SMTP host and port. Leave the defaults (`imap.gmail.com:993`, `smtp.gmail.com:465`) unless you know you need others. |

What xMender does and does not do with your inbox:

- It only reads the **Inbox** folder, and opens it read-only. Mail is never marked as read, moved, labelled or deleted.
- Only mail that arrives **after** you connect is processed. See [How mail is checked](#mail).
- Changing the address of an existing inbox starts over from "now" for the new address.

The address is shown masked (`j*****e@gmail.com`); hold the eye button to see it in full. Only this page can reveal it.

### Deleting an inbox {#delete-gmail}

An inbox that tasks still use cannot be deleted. Delete or move those tasks first. Mail history for a deleted inbox is removed with it.

## Discord webhooks {#discord}

Tasks post messages to Discord through a channel **webhook**.

1. In Discord: channel settings → **Integrations** → **Webhooks** → **New Webhook** → **Copy Webhook URL**.
2. In xMender: **+ Add webhook**, give it a name, paste the URL and click **Save…**.
3. Choose **Send test & save** or **Skip test & save**.

Discord webhooks can only be checked by posting to them, so the test posts one real message titled `xMender Notification` into the channel. Skipping saves without any check; a wrong URL then only shows up when a task first sends.

Good to know:

- The **Name** is only a label inside xMender. Messages use the name and avatar set on the webhook in Discord; change them there.
- Old `discordapp.com` URLs and URLs with `/api/v9` and similar are accepted and cleaned up.
- **Forum channels**: add `?thread_id=…` to the URL to always post into one thread. Without it, each message starts a new thread named after the email subject.
- Messages never ping anyone, even if the text contains `@everyone` or a mention.
- If Discord rate-limits a webhook, xMender waits and retries a few times.

## HTTP webhooks {#http-webhooks}

Send email data to any web service: ntfy, Slack incoming webhooks, Home Assistant, n8n, your own API. Tasks use them with the [HTTP webhook step](#steps/http_post).

| Field | Meaning |
|---|---|
| Name | A label inside xMender. |
| URL | Must start with `https://` (or `http://`). Treated as a secret. Do not put a user name or password in it; use a header. |
| Method | `POST` or `PUT`. |
| Headers | Up to 10, for example `Authorization: Bearer …`. Values are stored encrypted and never shown again. `Host`, `Content-Type`, `Content-Length` and other transport headers are set by xMender and cannot be added. |

Saving asks whether to **send a test request**. The test sends `{"xmender": "test", "message": "…"}` as JSON; any 2xx answer counts as working. **Skip test & save** still checks that the address is allowed.

Rules for requests:

- **No private addresses.** Addresses on the xMender machine itself or the local network (for example `localhost`, `192.168.x.x`, `10.x.x.x`, `100.64.x.x`) are blocked, unless the server owner allowed them.
- **Redirects are not followed.** Use the final URL.
- Requests time out after 15 seconds. A `429`, `502`, `503` or `504` answer is retried once.
- Bodies can be at most 256 KB.
- The card shows only the host and the header names, never the full URL or header values.

## In use by tasks {#in-use}

An integration that a task uses cannot be deleted; the error lists the tasks. Change those tasks or delete them first.
