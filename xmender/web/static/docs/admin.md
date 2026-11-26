# Users and admin

The **Admin** page is only visible to admins. Each user's integrations, tasks and mail are private to them; admins manage accounts, not other people's tasks.

## Roles {#roles}

| Role | Can do |
|---|---|
| owner | The built-in `admin` account. Always an admin; cannot be deleted or demoted. Only the owner can change the owner account. |
| admin | Everything an owner can, except changing the owner. Has every permission automatically. Can be demoted or deleted by another admin. |
| user | Uses xMender with the permissions an admin gave them. |

## Permissions {#permissions}

| Permission | Gives access to |
|---|---|
| `integrations` | The **Integrations** page: connecting Gmail, Discord, HTTP webhooks and the Anthropic key. |
| `tasks` | The **Tasks** page: building and editing tasks. |

Everyone can use the Dashboard, Usage, Settings and Docs. Tick or untick a permission in the user's row; it applies right away. Admins always have all permissions, so their boxes are locked.

## Managing users {#users}

- **Add user**: username (3 to 32 characters: letters, digits, `_`, `.`, `-`), a password of at least 10 characters, and optionally **Admin**. New users get both permissions; untick them afterwards if needed.
- **Make admin / Remove admin**.
- **Set password**: sets a new password for the user and signs out all their sessions. They are not asked to change it, so tell them to change it under Settings.
- **Delete**: removes the user with **all** their integrations, tasks, mail history and usage. Cannot be undone. You cannot delete the owner or yourself.

## Account creation {#registration}

**Allow account creation from the login page** lets anyone who can open the xMender page create their own account. It is off by default. New accounts get the `integrations` and `tasks` permissions.

> [!warning]
> Only turn this on if the page is reachable just by people you trust, or turn it off again once they have signed up.

## Everyone's usage {#usage}

On the [Usage](#usage) page, admins can switch on **All users** to see the AI cost of the whole server.

## Server settings {#server}

How often mail is checked, how many emails per check, how long sign-ins last and whether the server is reachable from other machines are set by whoever runs the xMender server, not in the app. See the project's README.
