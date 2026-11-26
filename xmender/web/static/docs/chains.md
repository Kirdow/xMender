# Task chains

A chained task runs **after another task**, and only if that task ended the way you choose. Use chains to split a big task into parts, to add a fallback when something fails, or to reuse one AI result in several tasks.

## Setting up a chain {#setup}

- In the task list, click **+ Then** on a task to create a new task that runs after it. Or,
- in the task editor, pick a task under **Run after another task**.

Then tick under **Only when it** which results of the earlier task should start this one:

| Choice | The earlier task… |
|---|---|
| completed | finished without errors. |
| completed with errors | finished, but a step failed that was set to continue. |
| stopped by a filter | was stopped by a filter that did not match. |
| failed | stopped because of an error. |
| did not run | was paused, marked as needing a fix, or was itself a chained task whose condition was not met. |

At least one must be ticked. The default is **completed**.

Rules:

- Both tasks must use the **same inbox**. The list only offers tasks of the inbox you picked.
- No loops: a task cannot run after itself or after a task that (directly or not) runs after it.
- A chain can be at most 8 tasks long.

In the task list, chained tasks are indented below the task they run after, with `↳ after <task>` and the results they wait for. A pink **paused** chip means the earlier task is paused.

## How a chain runs {#running}

For each new email, tasks run in an order where every earlier task runs before the tasks chained after it. A chained task then checks how its earlier task ended on **this** email:

- If the result is one you ticked, the task runs. Its run log starts with a line `↳ After <task>` marked **pass**.
- If not, the task's result is `skipped` and the log line `↳ After <task>` is marked **skip** with the reason, for example *“Invoices” stopped by a filter; runs only if it completed*.

A skipped task counts as **did not run** for tasks chained after it, so a whole branch can be skipped at once.

## Using results from earlier tasks {#inherited}

A chained task can use the **named steps** of the task it runs after, and of that task's own earlier tasks, as if they were its own earlier steps:

- in [placeholders](#placeholders): `{{category.label}}`;
- in **Run this step** conditions, where they show as *Only if category (from Sorter)…*.

The editor lists the names you can use under **Run after another task**. Your own step names must be different from these.

Values come from the earlier task's run on the same email. If that task stopped early or a step failed, the steps that did not run have no values: their placeholders print as nothing (with a warning) and conditions see them as empty.

> [!tip]
> Pay for AI once: one task with a Classify step named `category` and nothing else, then several small chained tasks (*after Sorter, only when completed*) that each check `category.label` and post somewhere different.

## Changing a task others run after {#auto-update}

When you save a task that other tasks run after, xMender checks every task further down its chain:

- **Renamed steps** are followed: conditions and `{{old.…}}` placeholders in later tasks are updated to the new name.
- **Changing the inbox** moves the whole chain below it to the new inbox.
- If a later task would **break** (for example it uses a step you removed), a dialog lists those tasks and the reason. **Cancel** to keep editing, or **Save and pause them**. Paused tasks get a red **needs fixing** chip and are skipped until you open them, fix the problem and save.

After saving, a message sums up what happened, for example *Task saved; updated Notify; paused Archive.* A task marked **needs fixing** that becomes valid again is resumed automatically (*resumed …*).

## Deleting {#deleting}

A task that other tasks run after cannot be deleted. Point those tasks somewhere else (or set them to run on their own) or delete them first.
