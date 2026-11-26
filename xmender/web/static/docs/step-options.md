# Step options

Every step has an **Options** section at its bottom. When something is set, the collapsed line shows it, for example `Options · if category · inverted`.

## Name {#name}

Lets later steps use this step's outputs, in [placeholders](#placeholders) and in **Run this step** conditions.

- Starts with a letter; then lowercase `a-z`, `0-9` and `_`; at most 32 characters. Capitals are turned into lowercase.
- Must be unique in the task. In a [chained task](#chains) it must also differ from the named steps of the tasks it runs after.
- `email` is reserved for the email itself.
- Renaming a step updates later conditions and `{{old.…}}` placeholders in this task right away, and in chained tasks when you save.

Clearing the name is allowed; later steps then cannot refer to this step.

## If this step fails {#on-error}

| Choice | What happens |
|---|---|
| Stop the task (default) | The task ends with result `error`. |
| Continue with the next step | The step is marked **error** in the log, the task goes on, and finishes as `partial` (completed with errors). |

A failed step does not hand on any outputs: placeholders that use it are empty, and conditions on it see empty values.

Examples of failures: the AI model is unavailable, Discord rejects the webhook, an HTTP endpoint answers 500, a required extracted field is missing, a regular expression is too slow.

## Filters only {#filter-options}

### If it doesn't match {#on-no-match}

| Choice | What happens |
|---|---|
| Stop the task (default) | The task ends with result `stopped`. |
| Continue (later steps can check the result) | The step is marked **no-match**, `matched` is set to `false`, and the task goes on. |

"Continue" turns a filter into a check you can branch on: later steps use **Run this step → Only if *name*… match result → matched / did not match**.

### Invert {#invert}

**Pass when the filter does not match.** Inverts the result: a filter for newsletters becomes a filter for everything *except* newsletters. The log detail starts with `inverted:`. The `matched` output is the inverted result.

## Run this step {#run-this-step}

Run the step only when a condition on an **earlier named step** holds. If it does not hold, the step is marked **skip** with the reason (for example `condition not met: category.label equals invoice`) and the task moves on to the next step. A skipped step does not stop the task.

Pick, in order:

1. **Always**, or **Only if *name*…**: the earlier named step. In a chained task, named steps of earlier tasks in the chain are listed too, marked *(from task name)*.
2. The **output** to check, for example `label`. For filters, **match result** checks whether it matched.
3. The **comparison** and, if it needs one, a **value**.

| Comparison | Holds when |
|---|---|
| equals | The output equals the value. |
| does not equal | The output is anything else. |
| contains | The value appears anywhere in the output. |
| is one of | The output equals one of a comma list: `invoice, receipt`. |
| is not one of | The output equals none of them. |
| is set | The output is not empty. |
| is empty | The output is empty or missing. |
| matched | (filters) The filter matched. |
| did not match | (filters) The filter ran and did not match. |

All comparisons ignore upper/lower case and surrounding spaces. Yes/no values compare as `true` and `false`, so for an extracted yes/no field use **equals** `true`. A list output like `signals` compares as its comma text (`newsletter, bulk`), so use **contains** for one item.

If the step a condition refers to was itself skipped or failed, it has no outputs: **is empty** holds, **matched** and **did not match** both do not hold.

### Branching example {#branching}

A Classify step named `category` sorts mail into `invoice`, `personal` and `other`. Then:

| Step | Run this step |
|---|---|
| Template post to #bills | Only if category… label equals `invoice` |
| Webhook (Agent) to #inbox | Only if category… label equals `personal` |

Mail labelled `other` skips both and the task completes without posting anything.
