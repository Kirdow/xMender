"""Filter (Gmail category / label): uses Gmail's own sorting.

Category (Primary, Promotions, ...) and labels come from the IMAP fetch
(`X-GM-LABELS`, `X-GM-RAW "category:..."`), so they reflect Gmail's
classification and the user's Gmail filters at delivery time.
"""

from __future__ import annotations

from typing import Any

from ..gmail import CATEGORIES, ParsedEmail
from .base import Result, RunContext, RunState, StepConfigError, StepDef, StepError, ValidateContext


def _norm_label(label: str) -> str:
    return label.strip().lstrip("\\").lower()


def _validate(cfg: dict[str, Any], vctx: ValidateContext) -> dict[str, Any]:
    raw = cfg.get("categories")
    cats = [c for c in CATEGORIES if isinstance(raw, list) and c in raw]
    labels = ", ".join(
        p.strip() for p in str(cfg.get("labels") or "").split(",") if p.strip()
    )[:1000]
    if not cats and not labels:
        raise StepConfigError("pick a category or enter a label.")
    return {"categories": cats, "labels": labels}


def _run(cfg: dict[str, Any], mail: ParsedEmail, ctx: RunContext, state: RunState,
         entry: dict[str, Any]) -> Result:
    if mail.labels is None:
        raise StepError(
            "Gmail labels and categories are not available for this inbox (the IMAP server "
            "did not offer Gmail's extensions)."
        )
    have = {_norm_label(lb) for lb in mail.labels}
    out = {"category": mail.category or "", "labels": ", ".join(lb.lstrip("\\") for lb in mail.labels)}
    if cfg["categories"]:
        if mail.category is None:
            raise StepError("Gmail did not report a category for this email.")
        if mail.category not in cfg["categories"]:
            return Result(matched=False, vars=out, detail=f"category is {mail.category}")
    if cfg["labels"]:
        want = [_norm_label(x) for x in cfg["labels"].split(",") if x.strip()]
        hits = [w for w in want if w in have]
        if not hits:
            return Result(matched=False, vars=out, detail=f"none of the labels; has: {out['labels'] or 'none'}")
        return Result(matched=True, vars=out, detail=f"category {mail.category or '?'}, label {hits[0]}")
    return Result(matched=True, vars=out, detail=f"category is {mail.category}")


STEP = StepDef(
    type="filter_gmail", label="Filter (Gmail category / label)", group="filter",
    validate=_validate, run=_run, outputs=lambda cfg: ["category", "labels"],
)
