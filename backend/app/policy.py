"""Access policy. Deny by default; enforced in code, never by a model prompt.

A claim's readers are the INTERSECTION of the readers of every source supporting it,
so combining individually permitted records can never widen access.
"""
from __future__ import annotations

ROLES = ("departing", "reviewer", "engineer", "coordinator")
RECIPIENT_ROLES = ("engineer", "coordinator")

LABELS = {
    "public": {"title": "Public", "desc": "Safe for anyone on the project."},
    "team": {"title": "Team", "desc": "Project-internal planning, tasks and decisions."},
    "engineering": {"title": "Engineering", "desc": "Technical internals, infrastructure, workarounds."},
    "finance": {"title": "Finance", "desc": "Budgets, fees, sponsor amounts. Reviewer only."},
    "confidential": {"title": "Confidential", "desc": "Personal / HR. Never extracted or released."},
}

LABEL_READERS: dict[str, set[str]] = {
    "public": {"departing", "reviewer", "engineer", "coordinator"},
    "team": {"departing", "reviewer", "engineer", "coordinator"},
    "engineering": {"departing", "reviewer", "engineer"},
    "finance": {"reviewer"},
    "confidential": {"reviewer"},
}

# Labels whose text is never sent to extraction (and so can never reach a recipient).
NON_EXTRACTABLE = {"confidential"}


def readers_for_label(label: str) -> set[str]:
    return set(LABEL_READERS.get(label, {"reviewer"}))  # unknown label -> reviewer only


def readers_for_labels(labels: list[str] | set[str]) -> list[str]:
    labels = list(labels)
    if not labels:
        return ["reviewer"]
    allowed = set(ROLES)
    for label in labels:
        allowed &= readers_for_label(label)
    allowed.add("reviewer")  # the reviewer must be able to review everything
    return sorted(allowed)


def can_read_label(role: str, label: str) -> bool:
    return role in readers_for_label(label)


def role_matrix() -> list[dict]:
    return [
        {"label": k, **v, "readers": sorted(LABEL_READERS[k])} for k, v in LABELS.items()
    ]
