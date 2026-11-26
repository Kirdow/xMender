"""Registry of task step types, in step-picker order."""

from __future__ import annotations

from . import filter_agent, filter_builtin, filter_bulk, webhook_agent
from .base import StepDef

REGISTRY: dict[str, StepDef] = {
    s.type: s
    for s in (
        filter_builtin.STEP,
        filter_bulk.STEP,
        filter_agent.STEP,
        webhook_agent.STEP,
    )
}

GROUP_LABELS = {"filter": "Filters", "agent": "Agents", "action": "Actions"}
