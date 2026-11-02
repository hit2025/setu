"""Shared contract for every extractor: a candidate claim with an exact character span."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CLAIM_TYPES = ("decision", "owner", "task", "deadline", "dependency", "risk", "contact", "status", "note")

STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "by", "is", "are", "be",
    "now", "so", "our", "we", "i", "it", "this", "that", "then", "but", "has", "have", "will", "from",
    "at", "as", "still", "just", "after", "before", "into", "its", "their", "all", "per",
}

ALIASES = {
    "deployment target": "hosting platform",
    "hosting": "hosting platform",
    "deploy target": "hosting platform",
    "hosting provider": "hosting platform",
    "deployment platform": "hosting platform",
    "db": "database",
}


@dataclass
class Candidate:
    ctype: str
    subject: str
    attribute: str
    value: str
    statement: str
    passage_id: str
    start: int  # absolute offset in Source.content
    end: int
    modality: str = "fact"
    occurred_at: str = ""
    confidence: float = 0.8
    origin: str = "rules"
    extra: dict = field(default_factory=dict)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9#][a-z0-9#._\-]*", text.lower().replace("’", "'")) if t not in STOP]


def token_set(text: str) -> set[str]:
    out = set()
    for t in tokens(text):
        t = t.strip("._-")
        if t:
            out.add(t)
            if t.endswith("s") and len(t) > 3:
                out.add(t[:-1])
    return out


def containment(needle: str, hay: str) -> float:
    a, b = token_set(needle), token_set(hay)
    if not a:
        return 0.0
    return len(a & b) / len(a)


def normalize_key(text: str) -> str:
    t = re.sub(r"[^a-z0-9#._\- ]+", " ", text.lower())
    words = [w for w in t.split() if w]
    while words and words[0] in STOP | {"decision", "okay", "ok", "note", "also", "currently", "current", "new"}:
        words.pop(0)
    key = " ".join(words).strip(" .-")
    return ALIASES.get(key, key)


def normalize_value(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+now$", "", t)
    t = re.sub(r"[\s.;,:!]+$", "", t)
    t = re.sub(r"\s+", " ", t)
    return t
