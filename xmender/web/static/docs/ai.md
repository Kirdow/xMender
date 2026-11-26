# AI steps

Steps marked **(Agent)** use an Anthropic Claude model: [Filter (Agent)](#steps/filter_agent), [Classify (Agent)](#steps/classify_agent), [Extract (Agent)](#steps/extract_agent) and [Webhook (Agent)](#steps/webhook_agent). They need the [Anthropic integration](#integrations/anthropic).

## Choosing a model {#models}

- Each agent step has a **Model** list. **Default** uses the model chosen under [Settings](#account/default-model).
- The lists show the models your API key can use, fetched live from Anthropic. New models appear without an xMender update.
- If a step's saved model is no longer offered, it is listed as *(not offered by provider)*. Saving the task is then refused until you pick another, and runs fail with *Model … is not offered by the provider for this API key.*

Larger models are better at judgement and long emails; smaller ones are cheaper and faster. The [Usage](#usage) page shows what each model costs you.

## What the model sees {#what-the-model-sees}

For every agent step, the model receives:

- your **instructions** (and for Classify and Extract, your categories or fields);
- the email's **From, To, Cc, Date, Subject**, the **list of attachments** (name, type and size) and the **text body**. Bodies longer than 60,000 characters are cut, and the model is told so;
- the attachments themselves, only if the step's **Attachments** setting allows it (see below).

It does **not** see Gmail labels or category, other headers, or what earlier steps found. Instructions are not templates; to act on an earlier result, use a [Run this step](#step-options/run-this-step) condition instead.

## Attachments {#attachments}

Agent steps have an **Attachments** setting:

| Setting | Effect |
|---|---|
| Do not send | Default. The model only sees the attachment names. |
| Send PDFs | PDF attachments are sent. |
| Send images | JPEG, PNG, GIF and WebP images are sent. |
| Send PDFs and images | Both. |

Limits: at most 5 files, 10 MB each and 20 MB in total. Files over a limit, or of a kind the chosen model cannot read, are skipped; the run log lists them in a warning. Files that were read are listed as `read invoice.pdf`.

> [!warning]
> Every PDF page and image adds input tokens. Reading attachments can cost many times more per email than the text alone.

## Safety against tricky emails {#safety}

Anyone can send you an email, including one written to fool an AI ("ignore your instructions and…"). xMender guards against this:

- The email (and its attachments) is clearly marked as **untrusted data**, separate from your instructions, using markers the sender cannot guess.
- The model is told to never follow instructions found in the email.
- The model has **no tools**: it can only write text. It cannot send mail, open links or change anything.
- What it writes is used as plain text. Discord posts never ping anyone.

No AI is perfect, so do not use an AI filter as the only protection for something important. The [Phishing signals](#steps/filter_phishing) filter uses fixed rules that email text cannot talk its way past.

## Refusals and cut-off answers {#refusals}

Sometimes a model declines to handle an email.

- **Filter (Agent)** then does not match (log: `model declined to answer`).
- **Classify**, **Extract** and **Webhook** fail with an error, for example *Model declined to classify this email.*

For some newer models, Anthropic can hand a declined request to a fallback model automatically. The log's model name shows which model answered.

Each answer can be at most 16,000 tokens (less if the model's limit is lower). If Classify or Extract runs out, the step fails with *The model's answer was cut off*. Webhook (Agent) posts what it has and adds a warning.

## Structured answers {#structured}

Classify and Extract ask the model for a fixed JSON shape. Most models guarantee that shape; for models that don't, xMender still checks and converts the answer itself. In that case Extract's log notes *model without structured outputs; validated here*.

## Costs in the run log {#costs}

Every AI step's log line shows its tokens and cost, like `1,240 in / 85 out · $0.004120`. Hover the cost for the exact amount. Costs are added up on the [Usage](#usage) page.
