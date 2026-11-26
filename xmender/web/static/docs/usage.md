# Usage and cost

The **Usage** page shows how many AI tokens your tasks used and what that cost. Only [AI steps](#ai) cost anything; filters, Template post and HTTP webhook are free.

## Periods {#periods}

Pick **Today**, **7 days**, **30 days**, **This month** or **All time**. Days and months follow your browser's time zone.

Admins also get an **All users** switch to see everyone's usage together.

## The numbers {#numbers}

| Tile | Meaning |
|---|---|
| Cost | Estimated cost in US dollars. Hover it for the exact amount. If some calls used a model without a known price, it says how many. |
| Calls | Model attempts. A request that Anthropic handed to a fallback model counts as two. |
| Input tokens | Everything sent to the model, including the email, instructions and attachments. Cached tokens are listed separately below the number when there are any. |
| Output tokens | What the model wrote. |

Below are three tables: **By model** (with the price per million input and output tokens), **By task** and **By day**.

## How cost is calculated {#calculation}

- From the token counts Anthropic reports for each call, at Anthropic's list prices on the date shown under the tables (with a link to the pricing page).
- Each call's cost is stored when it happens, so later price changes do not rewrite history.
- Calls that failed still count when Anthropic billed them.
- When a model declines and Anthropic falls back to another model, the declined attempt is counted as billed. Your total can therefore be slightly **above** your Anthropic invoice, never below.
- A model xMender has no price for shows **price unknown**; its tokens are still counted.

Usage is recorded from the version of xMender that added this page onward; earlier calls are not included.

For the real bill, see your Anthropic console.
