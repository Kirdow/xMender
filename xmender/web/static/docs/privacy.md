# Security and privacy

## What xMender stores {#stored}

| Data | Kept |
|---|---|
| Passwords, App Passwords, API keys, webhook URLs and header values | Encrypted. Never shown again after saving. Your own login password is stored only as a one-way hash. |
| Processed emails | Sender, recipients, subject, date and the first 300 characters of text. **Not** the full body and not attachments. |
| Run logs | What each step did, including AI replies and the messages or bodies that were sent (up to 4,000 characters each). |
| Usage | Tokens and cost per AI call. |

If you [install xMender as an app](#account/install), your device keeps a copy of the app's own files (page layout, scripts, icons and docs pages) so it can open without a connection. Mail, tasks, settings and anything from your account are never stored there.

Your inbox itself is opened read-only: xMender never marks, moves, labels or deletes mail.

## What leaves the server {#sent}

| Where | What |
|---|---|
| Anthropic | For each **AI step** only: your instructions and the email (headers listed in [AI steps](#ai/what-the-model-sees), the body, and attachments if you allowed them). Steps without AI send nothing to Anthropic. |
| Discord | The message your step posts. |
| HTTP webhooks | The body you wrote, with placeholders filled in. |
| Google | Only the login and mail check for your inbox. |

## Masked addresses and keys {#masking}

Connected Gmail addresses are shown masked (`j*****e@gmail.com`), and the Anthropic key as `sk-ant-••••`. On the **Integrations** page you can hold the eye button to see them. No other page can reveal them.

## Protection built in {#protections}

- **AI steps** treat email content as untrusted data and have no tools. See [AI steps → Safety](#ai/safety).
- **Discord** posts never ping `@everyone`, roles or users.
- **HTTP webhooks** cannot reach the xMender machine or your local network (unless the server owner allows it), and do not follow redirects. See [HTTP webhooks](#integrations/http-webhooks).
- **Placeholders** insert values as plain text; an email cannot inject placeholders or template code.
- **Sign-in** uses a cookie that scripts cannot read and other sites cannot send.
- Other users cannot see your integrations, tasks or mail.

## Deleting your data {#deleting}

- Delete a task: its past runs stay on the Dashboard.
- Delete a Gmail inbox: its processed-mail history and runs are deleted with it.
- An admin deleting your account removes everything that belongs to it.
