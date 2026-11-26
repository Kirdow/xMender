"""Task chains: a task may run only after another task of the same inbox
ended with one of the chosen statuses.

A chained task inherits the named step outputs of its parent (and the
parent's own ancestors), so its conditions and templates can use them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .pipeline import StepConfigError, step_outputs

# Parent statuses a chain can wait for. `skipped` means the parent did not
# run: it is paused, or its own chain condition was not met.
STATUSES = ("completed", "partial", "stopped", "error", "skipped")
STATUS_LABELS = {
    "completed": "completed",
    "partial": "completed with errors",
    "stopped": "stopped by a filter",
    "error": "failed",
    "skipped": "did not run",
}
DEFAULT_STATUSES = ["completed"]
MAX_DEPTH = 8


@dataclass
class Node:
    """The parts of a task chains care about."""

    id: int
    name: str
    inbox_id: int
    steps: list[dict[str, Any]]
    enabled: bool = True
    parent_id: int | None = None
    statuses: list[str] = field(default_factory=lambda: list(DEFAULT_STATUSES))


def node(task: Any) -> Node:
    return Node(
        id=task.id, name=task.name, inbox_id=task.gmail_integration_id, steps=list(task.steps or []),
        enabled=bool(task.enabled), parent_id=task.depends_on_id,
        statuses=list(task.depends_on_status or DEFAULT_STATUSES),
    )


def validate(
    raw: Any, task_id: int | None, inbox_id: int, nodes: dict[int, Node],
) -> tuple[int | None, list[str] | None]:
    """Normalise a `depends_on` body value into (parent id, statuses)."""
    if raw in (None, {}, ""):
        return None, None
    if not isinstance(raw, dict):
        raise StepConfigError("Invalid chain setting.")
    try:
        pid = int(raw.get("task_id"))
    except (TypeError, ValueError):
        return None, None
    parent = nodes.get(pid)
    if parent is None:
        raise StepConfigError("The task this one runs after no longer exists.")
    if parent.inbox_id != inbox_id:
        raise StepConfigError("A chained task must use the same inbox as the task it runs after.")
    statuses = raw.get("status")
    if not isinstance(statuses, list):
        statuses = DEFAULT_STATUSES
    statuses = [s for s in STATUSES if s in statuses]
    if not statuses:
        raise StepConfigError("Pick at least one result of the earlier task to run after.")
    depth, cur, seen = 1, parent, set()
    while cur is not None:
        if cur.id == task_id or cur.id in seen:
            raise StepConfigError(f"Running after “{parent.name}” would make a loop.")
        seen.add(cur.id)
        cur = nodes.get(cur.parent_id) if cur.parent_id else None
        depth += 1
    if depth > MAX_DEPTH + 1:
        raise StepConfigError(f"A chain can be at most {MAX_DEPTH} tasks long.")
    return pid, statuses


def inherited_outputs(parent_id: int | None, nodes: dict[int, Node]) -> dict[str, set[str]]:
    """Named step outputs available to a task chained after `parent_id`."""
    chain: list[Node] = []
    cur = nodes.get(parent_id) if parent_id else None
    while cur is not None and cur not in chain and len(chain) <= MAX_DEPTH:
        chain.append(cur)
        cur = nodes.get(cur.parent_id) if cur.parent_id else None
    out: dict[str, set[str]] = {}
    for n in reversed(chain):  # oldest ancestor first; later names win
        for s in n.steps:
            if s.get("name"):
                out[s["name"]] = step_outputs(s)
    return out


def descendants(task_id: int, nodes: dict[int, Node]) -> list[Node]:
    """Every task chained (directly or not) after `task_id`, parents first."""
    out: list[Node] = []
    frontier = [task_id]
    while frontier:
        kids = sorted((n for n in nodes.values() if n.parent_id in frontier and n not in out),
                      key=lambda n: n.id)
        out.extend(kids)
        frontier = [n.id for n in kids]
    return out


def order(nodes: Iterable[Node]) -> list[Node]:
    """Parents before children, otherwise by id. Tasks whose parent is not in
    the set keep their place."""
    items = sorted(nodes, key=lambda n: n.id)
    ids = {n.id for n in items}
    done: set[int] = set()
    out: list[Node] = []

    def visit(n: Node, path: set[int]) -> None:
        if n.id in done:
            return
        if n.parent_id in ids and n.parent_id not in path:
            visit(next(x for x in items if x.id == n.parent_id), path | {n.id})
        done.add(n.id)
        out.append(n)

    for n in items:
        visit(n, set())
    return out


def describe(statuses: list[str]) -> str:
    labels = [STATUS_LABELS.get(s, s) for s in statuses]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " or " + labels[-1]
