"""Secret and personal-data masking. Runs at ingestion, before anything is stored as
canonical text, so no model, citation or export can ever see the original values."""
from __future__ import annotations

import re
from collections import Counter

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("connection_string", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s'\"<>]+", re.I)),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}\b|\brzp_(?:live|test)_[A-Za-z0-9]{6,}\b|\bsk-[A-Za-z0-9_\-]{16,}\b|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bxox[abpr]-[A-Za-z0-9\-]{10,}\b")),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"(?<![\w-])(?:\+?\d{1,3}[\s\-]?)?(?:\d[\s\-]?){9,11}\d(?![\w-])")),
    ("gov_id", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b|\b[A-Z]{5}\d{4}[A-Z]\b")),
]

_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def mask_text(text: str) -> tuple[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    out = text
    for kind, pattern in _PATTERNS:
        def repl(m: re.Match[str], kind: str = kind) -> str:
            value = m.group(0)
            if kind == "phone" and (_DATE_LIKE.match(value.strip()) or "-" in value and value.count("-") == 2 and len(value) <= 10):
                return value
            if kind == "password":
                counts[kind] += 1
                return f"{m.group(1)}=[MASKED:SECRET]"
            counts[kind] += 1
            return f"[MASKED:{kind.upper()}]"
        out = pattern.sub(repl, out)
    return out, dict(counts)
