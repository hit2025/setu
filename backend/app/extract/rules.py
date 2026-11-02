"""Deterministic rule extractor.

Runs fully offline, so the product keeps working when no model is configured or the model
fails. Every value it emits is copied from the passage itself, so each claim has an exact
evidence span by construction."""
from __future__ import annotations

import re

from ..ingest import parse_csv_rows
from .base import Candidate, normalize_key

SENT_RE = re.compile(r"(?:[^.!?]|[.!?](?!\s|$))+(?:[.!?]+|$)")
LIST_PREFIX = re.compile(r"^(?:[-*+]\s+)?(?:\[[ xX]\]\s+)?(?:\d+[.)]\s+)?")
CHAT_PREFIX = re.compile(r"^\[(?P<ts>[^\]]*)\]\s+(?P<author>[\w.\-]+):\s+")
TAG_RE = re.compile(r"^(?P<tag>Decision|Proposal|Risk|Note|Blocker|Owner|Deadline|TODO|Action|Workaround)\s*:\s*", re.I)
DATE = r"\d{4}-\d{2}-\d{2}"
NAME = r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"

TASK_RE = re.compile(rf"^(?P<name>{NAME}) (?:to|will) (?P<task>.+?)(?: by (?P<date>{DATE}))?[.!]?$")
OWNS_RE = re.compile(rf"^(?P<name>{NAME}) (?:owns|is responsible for|will own|handles|maintains|leads) (?:the )?(?P<what>.+?)[.!]?$")
CONTACT_RE = re.compile(rf"^Contact (?P<name>{NAME}) (?:for|about|regarding) (?P<what>.+?)[.!]?$")
THROUGH_ME_RE = re.compile(r"^(?P<what>.+?) (?:goes|go|must go|needs to go) through me[.!]?$", re.I)
DEP_RE = re.compile(r"^(?P<a>.+?)\s+(?:depends on|is blocked by|is waiting on|requires|needs)\s+(?P<b>.+?)[.!]?$", re.I)
BEFORE_RE = re.compile(r"^(?P<a>.+?)\s+must (?:run|happen|be done|land|merge|be merged|ship)\s+before\s+(?P<b>.+?)[.!]?$", re.I)
DEADLINE_RE = re.compile(rf"(?P<subj>\b[A-Za-z][\w .#\-]{{2,40}}?)\s+(?:deadline|due date|is due|due)\s*(?:is|:|-|on)?\s*(?:now\s+)?(?P<date>{DATE})")
KV_COLON_RE = re.compile(r"^(?P<key>[A-Za-z][\w .#/+\-]{1,40}?)\s*:\s*(?P<val>.+?)[.]?$")
KV_IS_RE = re.compile(r"\b(?P<key>(?i:[a-z][a-z0-9 #.\-]{2,40}?))\s+(?:is|are)\s+(?:now\s+)?(?P<val>[A-Z0-9][^,;]*?)(?:\s+now)?[.!]?$")
STATUS_RE = re.compile(r"\b(?P<ref>(?:PR|Issue|issue|pr) #\d+)\b.*?\b(?P<state>still open|open|merged|closed|in review)\b")
ACT_PR_RE = re.compile(r"^\[(?P<ts>[^\]]*)\]\s+PR #(?P<id>\d+) \((?P<state>[\w ]+)\) by (?P<author>[\w.\-]+): (?P<title>.+)$")
ACT_ISSUE_RE = re.compile(r"^\[(?P<ts>[^\]]*)\]\s+Issue #(?P<id>\d+) \((?P<state>[\w ]+), (?:unassigned|assigned to (?P<assignee>[\w.\-]+))\): (?P<title>.+)$")
ACT_COMMIT_RE = re.compile(r"^\[(?P<ts>[^\]]*)\]\s+Commit (?P<sha>\w+) by (?P<author>[\w.\-]+): (?P<msg>.+)$")

PROPOSAL_HINT = re.compile(r"\b(maybe|perhaps|propose|proposal|should we|what if|could we|might switch|consider)\b", re.I)
RISK_HINT = re.compile(r"\b(workaround|not idempotent|may fail|might fail|might break|no load test|risk|duplicate|fragile|flaky|pending|manually)\b", re.I)
TACIT_HINT = re.compile(r"\b(workaround|manually|by hand|only i know|undocumented|hack)\b", re.I)
SKIP_KEYS = {"attendees", "last updated", "date", "updated", "author", "support inbox", "temp staging db url"}

HEADING_HINTS = {
    "decision": "decision", "proposal": "proposal", "risk": "risk", "action": "task",
    "todo": "task", "ownership": "owner", "owner": "owner", "contact": "contact",
    "stack": "decision", "release": "release",
}


def _heading_kind(heading: str) -> str:
    h = heading.lower()
    for k, v in HEADING_HINTS.items():
        if k in h:
            return v
    return ""


class _Ctx:
    def __init__(self, people: dict[str, str]):
        self.people = people  # handle or first name (lower) -> full name

    def person(self, name: str) -> str:
        key = name.strip().lower()
        if key in self.people:
            return self.people[key]
        first = key.split()[0] if key else key
        return self.people.get(first, name.strip())


def _cap(s: str) -> str:
    s = s.strip().rstrip(".")
    return s[:1].upper() + s[1:] if s else s


def _sentence_claims(sent: str, s0: int, pid: str, heading_kind: str, author: str, ts: str, ctx: _Ctx) -> list[Candidate]:
    """s0 is the absolute offset of `sent` in Source.content."""
    out: list[Candidate] = []
    lead = len(sent) - len(sent.lstrip())
    sent = sent.strip()
    s0 += lead
    if not sent:
        return out
    tag = ""
    m = TAG_RE.match(sent)
    body, b0 = sent, s0
    if m:
        tag = m.group("tag").lower()
        body, b0 = sent[m.end():], s0 + m.end()

    def cand(ctype, subject, attribute, value, statement, vstart=None, vend=None, **kw) -> Candidate:
        # Evidence span is the whole sentence: the exact text a reviewer needs to judge it.
        return Candidate(ctype, subject, attribute, value, statement, pid, s0, s0 + len(sent),
                         occurred_at=ts, **kw)

    is_question = sent.endswith("?")
    if tag == "proposal" or heading_kind == "proposal" or (PROPOSAL_HINT.search(sent) and not tag == "decision"):
        if tag == "proposal" or heading_kind == "proposal" or "propos" in sent.lower() or "maybe" in sent.lower():
            text = body.rstrip("?.! ")
            out.append(cand("decision", text, "proposal: " + normalize_key(text), text,
                            f"Proposal (not a decision): {text}", modality="proposal", confidence=0.6))
            return out
    if is_question:
        return out

    if tag in ("risk", "workaround", "blocker") or heading_kind == "risk" or (RISK_HINT.search(body) and not DEP_RE.match(body) and not BEFORE_RE.match(body)):
        text = body.rstrip(". ")
        tacit = bool(TACIT_HINT.search(text)) or tag == "workaround"
        subject = " ".join(text.split()[:7])
        out.append(cand("risk", subject, "risk: " + normalize_key(text)[:120], text,
                        ("Tacit workaround: " if tacit else "Risk: ") + text,
                        modality="tacit" if tacit else "fact", confidence=0.75))
        return out

    mt = TASK_RE.match(body)
    if mt and (heading_kind == "task" or tag in ("todo", "action") or mt.group("date")):
        task = _cap(mt.group("task"))
        owner = ctx.person(mt.group("name"))
        key = normalize_key(task)
        out.append(cand("task", task, "task: " + key, "open", f"Task: {task}", confidence=0.8))
        out.append(cand("owner", task, "owner: " + key, owner, f"{owner} owns '{task}'", confidence=0.8))
        if mt.group("date"):
            out.append(cand("deadline", task, "deadline: " + key, mt.group("date"),
                            f"'{task}' is due {mt.group('date')}", confidence=0.85))
        return out

    mo = OWNS_RE.match(body)
    if mo:
        what = _cap(mo.group("what"))
        owner = ctx.person(mo.group("name"))
        out.append(cand("owner", what, "owner: " + normalize_key(what), owner, f"{owner} owns {what[0].lower() + what[1:]}"))
        return out

    mc = CONTACT_RE.match(body)
    if mc:
        what = _cap(mc.group("what"))
        who = ctx.person(mc.group("name"))
        out.append(cand("contact", what, "contact: " + normalize_key(what), who, f"Contact {who} for {what[0].lower() + what[1:]}"))
        return out
    mm = THROUGH_ME_RE.match(body)
    if mm and author:
        what = _cap(mm.group("what"))
        who = ctx.person(author)
        out.append(cand("contact", what, "contact: " + normalize_key(what), who,
                        f"Contact {who} for {what[0].lower() + what[1:]}", confidence=0.75))
        return out

    mb = BEFORE_RE.match(body)
    if mb:
        a, b = _cap(mb.group("a")), _cap(mb.group("b"))
        out.append(cand("dependency", b, f"dependency: {normalize_key(b)} -> {normalize_key(a)}", a,
                        f"'{b}' requires '{a}' first"))
        return out
    md = DEP_RE.match(body)
    if md:
        a, b = _cap(md.group("a")), md.group("b").strip().rstrip(".")
        out.append(cand("dependency", a, f"dependency: {normalize_key(a)} -> {normalize_key(b)}", b,
                        f"'{a}' depends on {b}"))
        return out

    mdl = DEADLINE_RE.search(body)
    if mdl:
        subj = _cap(normalize_key(mdl.group("subj")))
        out.append(cand("deadline", subj, "deadline: " + normalize_key(subj), mdl.group("date"),
                        f"{subj} deadline is {mdl.group('date')}", confidence=0.85))
        return out

    ms = STATUS_RE.search(body)
    if ms:
        ref = ms.group("ref").replace("pr", "PR").replace("issue", "Issue")
        state = ms.group("state").replace("still ", "")
        out.append(cand("status", ref, "status: " + normalize_key(ref), state, f"{ref} is {state}", confidence=0.7))
        return out

    mk = KV_COLON_RE.match(body)
    if not mk or " " in mk.group("key").strip() and len(mk.group("key").split()) > 5:
        mk = None
    if mk is None:
        mk = KV_IS_RE.search(body)
    if mk:
        key = normalize_key(mk.group("key"))
        val = mk.group("val").strip().rstrip(".")
        if key and val and key not in SKIP_KEYS and "[MASKED" not in val and len(key.split()) <= 5:
            modality = "decision" if (tag == "decision" or heading_kind in ("decision",)) else "fact"
            out.append(cand("decision", _cap(key), key, val, f"{_cap(key)}: {val}", modality=modality,
                            confidence=0.85 if modality == "decision" else 0.7))
    return out


def extract_text(source, passages, people: dict[str, str]) -> list[Candidate]:
    ctx = _Ctx(people)
    out: list[Candidate] = []
    for p in passages:
        text, base = p.text, p.start
        # Repository activity lines have a fixed shape.
        if (m := ACT_PR_RE.match(text)):
            ref = f"PR #{m.group('id')}"
            out.append(Candidate("status", ref, "status: " + normalize_key(ref), m.group("state"),
                                 f"{ref} '{m.group('title')}' is {m.group('state')} (author {ctx.person(m.group('author'))})",
                                 p.id, base, base + len(text), occurred_at=p.occurred_at, confidence=0.95))
            continue
        if (m := ACT_ISSUE_RE.match(text)):
            title = f"Issue #{m.group('id')}: {m.group('title')}"
            key = normalize_key(f"issue #{m.group('id')}")
            state = m.group("state")
            out.append(Candidate("task", title, "task: " + key, state, f"Open issue: {m.group('title')}" if state == "open" else f"Issue {state}: {m.group('title')}",
                                 p.id, base, base + len(text), occurred_at=p.occurred_at, confidence=0.95))
            if m.group("assignee"):
                who = ctx.person(m.group("assignee"))
                out.append(Candidate("owner", title, "owner: " + key, who, f"{who} owns {title}",
                                     p.id, base, base + len(text), occurred_at=p.occurred_at, confidence=0.95))
            continue
        if (m := ACT_COMMIT_RE.match(text)):
            ref = f"Commit {m.group('sha')}"
            out.append(Candidate("status", ref, "status: " + normalize_key(ref), "committed",
                                 f"{ref} by {ctx.person(m.group('author'))}: {m.group('msg')}",
                                 p.id, base, base + len(text), occurred_at=p.occurred_at, confidence=0.9))
            continue

        author = ""
        mc = CHAT_PREFIX.match(text)
        if mc:
            author = mc.group("author")
            text_body, b0 = text[mc.end():], base + mc.end()
        else:
            mp = LIST_PREFIX.match(text)
            text_body, b0 = text[mp.end():], base + mp.end()
        hk = _heading_kind(p.context)
        prev: list[Candidate] = []
        for sm in SENT_RE.finditer(text_body):
            sent = sm.group(0)
            if not sent.strip():
                continue
            found = _sentence_claims(sent, b0 + sm.start(), p.id, hk, author, p.occurred_at, ctx)
            # Resolve "it" in a workaround sentence to the thing the previous sentence was about.
            for c in found:
                if c.ctype == "risk" and c.modality == "tacit" and re.search(r"\bit\b", sent, re.I) and prev:
                    anchor = prev[-1].value if prev[-1].ctype == "dependency" else prev[-1].subject
                    c.subject = f"{anchor} workaround"
                    c.attribute = "risk: " + normalize_key(c.subject)
                    c.statement = f"Tacit workaround for {anchor}: {c.value}"
            out.extend(found)
            prev = found or prev
    return out


_FIELD_ALIASES = {
    "id": ("id", "key", "task_id", "ticket"),
    "title": ("title", "task", "summary", "name"),
    "owner": ("owner", "assignee", "assigned_to", "responsible"),
    "status": ("status", "state"),
    "due": ("due", "deadline", "due_date", "duedate"),
    "deps": ("depends_on", "dependencies", "blocked_by", "depends"),
}


def _pick(row: dict[str, str], name: str) -> str:
    for alias in _FIELD_ALIASES[name]:
        if row.get(alias):
            return row[alias]
    return ""


def extract_csv(source, passages, people: dict[str, str]) -> list[Candidate]:
    ctx = _Ctx(people)
    _, rows = parse_csv_rows(source.content)
    out: list[Candidate] = []
    for p, row in zip(passages, rows):
        title = _pick(row, "title")
        if not title:
            continue
        tid = _pick(row, "id")
        subject = f"{tid} {title}".strip()
        key = normalize_key(tid or title)
        line, base = p.text, p.start

        def span(value: str, after: int = 0) -> tuple[int, int]:
            i = line.find(value, after)
            if i < 0:
                return base, base + len(line)
            return base + i, base + i + len(value)

        ts, te = span(title)
        status = _pick(row, "status") or "open"
        out.append(Candidate("task", subject, "task: " + key, status, f"Task {subject} is {status.replace('_', ' ')}",
                             p.id, base, base + len(line), confidence=0.95, extra={"task_id": tid}))
        owner = _pick(row, "owner")
        if owner:
            os_, oe = span(owner, te - base)
            out.append(Candidate("owner", subject, "owner: " + key, ctx.person(owner), f"{ctx.person(owner)} owns {subject}",
                                 p.id, os_, oe, confidence=0.95))
        due = _pick(row, "due")
        if due:
            ds, de = span(due, te - base)
            out.append(Candidate("deadline", subject, "deadline: " + key, due, f"{subject} is due {due}",
                                 p.id, ds, de, confidence=0.95))
        deps = _pick(row, "deps")
        if deps:
            for dep in [d.strip() for d in re.split(r"[;|]", deps) if d.strip()]:
                ds, de = span(dep, te - base)
                out.append(Candidate("dependency", subject, f"dependency: {key} -> {normalize_key(dep)}", dep,
                                     f"{subject} depends on {dep}", p.id, ds, de, confidence=0.95))
    return out


def extract(source, passages, people: dict[str, str]) -> list[Candidate]:
    if source.kind == "csv":
        return extract_csv(source, passages, people)
    return extract_text(source, passages, people)
