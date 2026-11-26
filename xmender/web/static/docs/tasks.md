# Tasks

A task tells xMender what to do with new mail from one inbox. Open **Tasks** in the sidebar and click **+ New task** (you need a connected Gmail inbox first).

## Task settings {#settings}

| Setting | Meaning |
|---|---|
| Name | Shown in the task list, on the Dashboard and on the Usage page. |
| Inbox | The Gmail inbox whose new mail this task handles. A task belongs to exactly one inbox. |
| Run after another task | Optional. Makes this a chained task; see [Task chains](#chains). |
| Enabled | Paused tasks do not run. You can also flip the **Enabled** switch in the task list. |

## Steps {#steps}

A task is a list of steps that run from top to bottom for every new email. Pick a step type under the list and click **+ Add step**. Use the arrows on a step to move it, **✕** to remove it, and **?** to open its help.

There are three groups, each with its own colour:

| Group | Colour | What it does |
|---|---|---|
| Filters | Aqua | Decide whether the email goes on. When a filter does not match, the task **stops** there (unless you change that in its options). |
| Agents | Lime | Use AI to read the email: decide, sort it into a category, or pull out data. Need the [Anthropic integration](#integrations/anthropic). |
| Actions | Pink | Do something: post to Discord or send an HTTP request. |

The usual shape is: one or more filters first (cheap, no AI), then agents, then actions. Filters that need no AI cost nothing, so put them before AI steps to save money.

Every step type is described in the [Step reference](#steps). A task can have up to 50 steps.

### Step names {#names}

New steps get a name automatically (`filter`, `notify`, `extract`, …; a number is added when the name is taken). The name is shown as a small chip on the step. Names let later steps use what this step found:

- in **placeholders** inside templates, like `{{extract.amount}}` (see [Placeholders and templates](#placeholders));
- in the **Run this step** condition of a later step (see [Step options](#step-options)).

You can rename a step under **Options**. Later steps that use the old name are updated automatically when you leave the field.

## Saving {#saving}

**Save task** checks the whole task first. If anything is wrong, nothing is saved and the error says which step and what to fix, for example:

- *Step 2: pick a Discord webhook.*
- *Step 1: set at least one filter criterion.*
- *Step 3: body: …: step `bill` has no output `amont`.* (a typo in `{{bill.amont}}`)

Checks include: required fields are filled, every placeholder points at a field that exists, conditions point at earlier named steps, chosen models are offered by your API key, and regular expressions are valid.

## Run results {#run-status}

Every time a task runs on an email, it gets one of these results. You see them on the [Dashboard](#activity).

| On the Dashboard | In chain settings | Meaning |
|---|---|---|
| `completed` | completed | Every step ran (or was skipped by its own condition) without errors. |
| `partial` | completed with errors | A step failed, but it was set to continue on error, and the task finished. |
| `stopped` | stopped by a filter | A filter did not match and ended the task. This is normal: the email simply was not one this task cares about. |
| `error` | failed | A step failed and the task stopped there. |
| `skipped` | did not run | A chained task did not run because the task before it did not end the way it requires. |

## Pausing, editing and deleting {#manage}

- The **Enabled** switch pauses a task without losing anything.
- **Edit** opens the editor. Changes apply to the next email; past runs keep showing what happened at the time.
- **Delete** removes the task. Its past runs stay visible on the Dashboard. A task that other tasks run after cannot be deleted until those are changed or deleted.
- **+ Then** creates a new task that runs after this one.

### Needs fixing {#needs-fixing}

A red **needs fixing** chip means the task was paused automatically because a task it runs after changed in a way that breaks it (for example, a step it used was renamed away or removed). Open it, fix what the message says, and save to resume. See [Task chains](#chains/auto-update).

## Permissions {#permissions}

You need the **tasks** permission to see the Tasks page. Building useful tasks also needs integrations, which require the **integrations** permission. An admin grants both; see [Users and admin](#admin).
