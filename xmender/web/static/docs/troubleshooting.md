# Troubleshooting and FAQ

Start with the **Dashboard**: open the email and read the run log. It shows which step stopped or failed, and why. See [Reading a run log](#activity/run-log).

## Nothing happens with new mail {#nothing-happens}

- **Only new mail is processed.** Mail that was in the inbox before you connected it is never handled. Send yourself a test email.
- **Wait for the next check**, or press **Refresh now** on the Dashboard.
- Is the inbox card red? Then the check fails; see [Gmail errors](#troubleshooting/gmail).
- Is the task **enabled**, and set to the right **inbox**?
- Does the email show on the Dashboard with *No task ran on this email*? Then no enabled task existed for that inbox.
- Does it show `stopped`? A filter did not match. Open the run log to see which one and why.
- Does the task show **needs fixing**? See [Task chains](#chains/auto-update).

## Gmail {#gmail}

**IMAP: login rejected. Check the address and that the app password is correct.**
Use an App Password, not your Google password. Changing your Google password deletes all App Passwords; create a new one and paste it under **Integrations → Edit**.

**Use the plain Gmail address, without a `+` alias.** / **Enter a valid @gmail.com address.**
Only `@gmail.com` and `@googlemail.com` addresses work, without `+tag`.

**This Gmail address is already connected.**
Each address can be connected once per user.

**Gmail labels and categories are not available for this inbox.**
The [Gmail category / label filter](#steps/filter_gmail) only works with Google's own IMAP server. Check the server settings of the inbox.

**Gmail did not report a category for this email.**
Rare; Google could not be asked for the category during that check. The category filter fails for that email only.

## AI steps {#ai}

**No Anthropic integration is set up.**
Connect your key under [Integrations](#integrations/anthropic).

**No model chosen for this step and no default model in Settings.**
Pick a model on the step, or a [default model](#account/default-model).

**Model … is not offered by the provider for this API key.**
The model was retired or your key lost access. Pick another model on the step (or in Settings) and save.

**Anthropic rejected the API key.**
The key was deleted or disabled. Replace it under Integrations.

**Anthropic rate limit hit; try again later.**
Too many calls at once for your Anthropic account's limits. Set the step to continue on error, or put cheaper filters before AI steps so fewer emails reach them.

**Required field(s) not found: …**
An Extract field marked **Required** had no value in this email. Untick Required if the value is sometimes missing, or improve the field's description.

**The model's answer was cut off (max_tokens).**
The answer was too long. Use fewer Extract fields or shorter descriptions.

**Model declined to … this email.**
The model refused. Try another model, or reword the instructions. See [Refusals](#ai/refusals).

**Extract gives `1250` instead of `12.50`.**
The email uses a decimal comma. See the warning in [Extract (Agent)](#steps/extract_agent).

## Discord {#discord}

**Discord rejected the webhook (deleted or wrong token).**
The webhook was deleted in Discord, or the URL is wrong. Create a new webhook and paste its URL under **Integrations → Edit**.

**Discord kept rate-limiting the webhook.**
Too many messages in a short time. Combine tasks, or filter more strictly.

**A forum channel gets a new thread for every message.**
Add `?thread_id=<thread id>` to the webhook URL to post into one thread.

**The message shows a different name or picture than I typed in xMender.**
That is by design: the name in xMender is just a label. Change the name and avatar on the webhook in Discord.

## HTTP webhooks {#http}

**… resolves to an address that cannot be used.**
The host points to the xMender machine or a local network address. Use a public address, or ask the server owner to allow local addresses.

**… answered with a redirect (HTTP 30x); redirects are not followed.**
Use the final URL, often with `https://` or a trailing `/`.

**… did not answer within 15 s.** / **Could not reach …**
The service is down or unreachable from the xMender server.

**… returned HTTP 400** (or another 4xx)
The service did not accept the body. Compare the body in the run log with what the service expects. A 401 or 403 usually means a missing or wrong `Authorization` header.

**the body is not valid JSON (…)**
Put every placeholder inside quotes: `"{{email.subject}}"`, not `{{email.subject}}`. See [JSON bodies](#placeholders/json).

## Placeholders {#placeholders}

**… is not a valid placeholder; use {{step.field}}.**
Every placeholder needs a source and a field, like `{{email.subject}}`.

**… refers to `x`, which is not a named earlier step.**
Give the step a name under **Options**, check the spelling, and make sure it is **above** this step.

**step `x` has no output `y`.**
Check the step's outputs in the [Step reference](#steps). For Extract, the field key must match exactly.

**Warning in the run log: `x.y had no value`.**
The step `x` did not run for this email (it was skipped by its condition, failed, or its task stopped earlier). Use `| default:…` or a **Run this step** condition.

**An extracted value is empty in the message.**
The model found nothing for it. Use `{{x.y | default:unknown}}`.

## Other {#other}

**The time window filter uses the wrong time.**
Set your time zone under [Settings](#account/time-zone), or a zone on the step. The log's `local_time` shows the time it used.

**the regular expression … took too long and was stopped.**
Simplify the pattern; avoid nested repeats like `(a+)+`.

**Usage shows "price unknown".**
The model is newer than xMender's price list. Tokens are still counted; the cost appears after an xMender update.

**My browser offers no way to install xMender.**
Installing needs `https://`, or `localhost` on the same computer; see [Installing xMender as an app](#account/install). Firefox on desktop does not install sites as apps. On iPhone and iPad use Safari's **Share → Add to Home Screen**.

**The installed app on iPhone asks me to sign in again.**
Home-screen apps on iOS keep their own sign-in, separate from Safari. Sign in once inside the app.

**I forgot my password.**
Ask an admin to set a new one under **Admin → Set password**. The owner account (`admin`) can only be changed by itself, so xMender has no way yet to recover a forgotten owner password. Keep it in a password manager.

**Which version of xMender is this?**
The footer at the bottom of every page shows the commit the server is running and its date. Click the short hash to open that commit and its changes on GitHub. **+modified** means the server runs local changes on top of that commit. The footer shows the version the server started with, so after an update it changes only once the server is restarted.
