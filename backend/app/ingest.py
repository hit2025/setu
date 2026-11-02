"""Stage 01 - Connect. Normalise authorised uploads into canonical, masked text with
stable passage IDs, character offsets, content hashes and access labels."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field

from .masking import mask_text

SUPPORTED = {".md": "markdown", ".markdown": "markdown", ".txt": "text", ".csv": "csv", ".json": "json"}


class IngestError(ValueError):
    pass


@dataclass
class PassageDraft:
    idx: int
    start: int
    end: int
    text: str
    context: str = ""
    occurred_at: str = ""


@dataclass
class CanonicalDoc:
    kind: str
    content: str
    raw_hash: str
    content_hash: str
    masked: dict[str, int]
    passages: list[PassageDraft] = field(default_factory=list)
    authored_at: str = ""


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def detect_kind(filename: str) -> str:
    lower = filename.lower()
    for ext, kind in SUPPORTED.items():
        if lower.endswith(ext):
            return kind
    raise IngestError(f"Unsupported file type for '{filename}'. Use .md, .txt, .csv or .json.")


def _fmt_ts(ts: str) -> str:
    if not ts:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", ts)
    return f"{m.group(1)} {m.group(2)}" if m else ts[:16]


def _json_to_lines(data) -> tuple[list[tuple[str, str, str]], str]:
    """Return (line, context, occurred_at) triples and a document timestamp."""
    lines: list[tuple[str, str, str]] = []
    doc_time = ""
    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        channel = str(data.get("channel", "chat"))
        doc_time = str(data.get("exported_at", ""))
        for msg in data["messages"]:
            if not isinstance(msg, dict):
                continue
            ts = str(msg.get("ts") or msg.get("time") or msg.get("timestamp") or "")
            author = str(msg.get("author") or msg.get("user") or msg.get("from") or "unknown")
            text = str(msg.get("text") or msg.get("message") or msg.get("body") or "").replace("\n", " ").strip()
            if text:
                lines.append((f"[{_fmt_ts(ts)}] {author}: {text}", f"{channel} / {author}", ts))
        return lines, doc_time
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        for ev in data:
            ts = str(ev.get("at") or ev.get("ts") or ev.get("created_at") or ev.get("date") or "")
            etype = str(ev.get("type", "event")).lower()
            author = ev.get("author") or ev.get("user") or ""
            if etype in ("pull_request", "pr"):
                line = f"PR #{ev.get('id')} ({ev.get('state', 'unknown')}) by {author}: {ev.get('title', '')}"
            elif etype == "commit":
                line = f"Commit {ev.get('sha', '')} by {author}: {ev.get('message', '')}"
            elif etype == "issue":
                assignee = ev.get("assignee")
                who = f"assigned to {assignee}" if assignee else "unassigned"
                line = f"Issue #{ev.get('id')} ({ev.get('state', 'unknown')}, {who}): {ev.get('title', '')}"
            else:
                parts = [f"{k}={v}" for k, v in ev.items() if k not in ("at", "ts") and not isinstance(v, (dict, list))]
                line = f"{etype}: " + ", ".join(parts)
            lines.append((f"[{_fmt_ts(ts)}] {line}".replace("\n", " "), "repository activity", ts))
            doc_time = max(doc_time, ts)
        return lines, doc_time

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        else:
            lines.append((f"{path}: {node}".replace("\n", " "), "json", ""))

    walk(data, "")
    return lines, doc_time


def canonicalize(filename: str, raw: bytes) -> CanonicalDoc:
    kind = detect_kind(filename)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError(f"'{filename}' is not valid UTF-8 text.") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_hash = sha256(raw)

    if kind == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IngestError(f"'{filename}' is not valid JSON: {exc.msg}") from exc
        triples, doc_time = _json_to_lines(data)
        masked_lines, masked_totals = [], {}
        for line, ctx, ts in triples:
            m, counts = mask_text(line)
            for k, v in counts.items():
                masked_totals[k] = masked_totals.get(k, 0) + v
            masked_lines.append((m, ctx, ts))
        content = "\n".join(m for m, _, _ in masked_lines) + "\n"
        passages, pos = [], 0
        for i, (m, ctx, ts) in enumerate(masked_lines):
            passages.append(PassageDraft(i, pos, pos + len(m), m, ctx, ts))
            pos += len(m) + 1
        return CanonicalDoc(kind, content, raw_hash, sha256(content), masked_totals, passages, doc_time)

    content, masked = mask_text(text)
    passages: list[PassageDraft] = []
    authored = ""
    m = re.search(r"(?i)(?:last updated|date)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", content) or re.search(
        r"(\d{4}-\d{2}-\d{2})", content.split("\n", 1)[0])
    if m:
        authored = m.group(1)

    if kind == "csv":
        rows = content.split("\n")
        header = rows[0] if rows else ""
        pos = len(header) + 1
        for line in rows[1:]:
            if line.strip():
                passages.append(PassageDraft(len(passages), pos, pos + len(line), line, header))
            pos += len(line) + 1
        if not passages:
            raise IngestError(f"'{filename}' has no data rows.")
        # Validate it parses as CSV at all.
        list(csv.reader(io.StringIO(content)))
        return CanonicalDoc(kind, content, raw_hash, sha256(content), masked, passages, authored)

    heading = ""
    pos = 0
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
        elif stripped:
            lead = len(line) - len(line.lstrip())
            passages.append(PassageDraft(len(passages), pos + lead, pos + len(line.rstrip()), stripped, heading))
        pos += len(line) + 1
    return CanonicalDoc(kind, content, raw_hash, sha256(content), masked, passages, authored)


def parse_csv_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content))
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    rows = []
    for row in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    return fields, rows
