# Account and settings

## First sign-in {#first-sign-in}

Every xMender server has one built-in owner account called `admin`. The first time someone opens xMender, it asks for the **temporary password** that the server printed when it started, and a new password of your choice.

- The temporary password is in the xMender service output. With systemd it shows up in `journalctl -u xmender`.
- Your new password must be at least 10 characters and different from the temporary one.

Other people get an account from an admin (see [Users and admin](#admin)), or create one themselves on the login page if an admin has turned on **account creation**.

## Creating an account {#register}

When account creation is on, the login page shows **No account? Create one**.

- Usernames are 3 to 32 characters: letters, digits, `_`, `.` and `-`.
- Passwords are at least 10 characters.
- New accounts can use both **Integrations** and **Tasks** right away.

## Signing in and out {#sessions}

You stay signed in in that browser for a while (14 days by default; the server owner can change it). **Log out** is the arrow button next to your name at the bottom of the sidebar.

Changing your password signs out your other browsers. When an admin sets a new password for you, all your sessions are signed out.

## Settings page {#settings}

Open **Settings** in the sidebar.

### Default model {#default-model}

The AI model used by every agent step that does not pick its own model. The list comes straight from Anthropic, so it only shows models your API key can use. **Reload list** fetches it again; otherwise it is kept for about 10 minutes.

If no default is set and a step has no model of its own, that step fails with *No model chosen for this step and no default model in Settings.* See [AI steps](#ai).

### Time zone {#time-zone}

Your time zone is taken from your browser the first time you sign in, and you can change it here. It is used by:

- the [Time window filter](#steps/filter_time), unless the step sets its own zone. Without any zone, that filter uses UTC and adds a warning to the run.

The **Usage** page always uses your browser's time zone for its days and periods.

### Password {#password}

Enter your current password and the new one twice. At least 10 characters.

## What each page is for {#pages}

| Page | What you do there | Who sees it |
|---|---|---|
| Dashboard | See your inboxes, check for mail now, read what every task did with each email. | Everyone |
| Tasks | Build and edit tasks. | Users with the **tasks** permission |
| Integrations | Connect Gmail, Discord, HTTP webhooks and the Anthropic API. | Users with the **integrations** permission |
| Usage | AI tokens and cost. | Everyone |
| Settings | Default model, time zone, password. | Everyone |
| Admin | Users, permissions and account creation. | Admins |
| Docs | This documentation. | Everyone, also without signing in at `/docs` |
