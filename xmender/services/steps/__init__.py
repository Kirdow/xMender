"""Registry of task step types, in step-picker order."""

from __future__ import annotations

from . import (
    classify_agent, extract_agent, filter_agent, filter_builtin, filter_bulk, filter_phishing, filter_sender, filter_time,
    http_post, template_post, webhook_agent,
)
from .base import StepDef

REGISTRY: dict[str, StepDef] = {
    s.type: s
    for s in (
        filter_builtin.STEP,
        filter_bulk.STEP,
        filter_time.STEP,
        filter_sender.STEP,
        filter_phishing.STEP,
        filter_agent.STEP,
        classify_agent.STEP,
        extract_agent.STEP,
        webhook_agent.STEP,
        template_post.STEP,
        http_post.STEP,
    )
}

GROUP_LABELS = {"filter": "Filters", "agent": "Agents", "action": "Actions"}
