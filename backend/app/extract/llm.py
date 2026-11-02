"""Claude-based structured extraction.

The model only PROPOSES typed claims and an exact supporting quote per claim. Code then
anchors every quote to an exact character span; anything that does not match verbatim is
rejected. The model never decides access, conflicts, readiness or approval."""
from __future__ import annotations

import json
import logging
import os

import anthropic

from ..config import LLM_MODEL, LLM_TIMEOUT_S
from .base import CLAIM_TYPES, Candidate, normalize_key

log = logging.getLogger("setu.llm")

SYSTEM = """You extract a project-handover claim ledger from ONE source document of a software team.
Return only claims that the text explicitly states. Never infer, summarise across passages, or guess.

Claim types:
- decision: a chosen setting/approach (attribute = the setting, value = the choice). If text is only a suggestion, set modality=proposal.
- owner: who owns a component or task (subject = the thing, value = person full name).
- task: a piece of work (subject = task title, value = its status, or "open").
- deadline: a due date (subject = what is due, value = ISO date YYYY-MM-DD).
- dependency: X needs Y first (subject = X, value = Y).
- risk: a known risk, fragile area or undocumented manual workaround (modality=tacit for workarounds).
- contact: who to ask for something (subject = topic, value = person).
- status: state of a PR/issue/component (subject = item, value = state).

Rules:
- quote MUST be copied character-for-character from exactly one passage (a full sentence is best). It is verified by code; paraphrased quotes are discarded.
- value must appear inside quote whenever possible.
- attribute is a short lowercase key naming what the claim is about, e.g. "hosting platform", "release v1.2 deadline", "owner: run migration 014".
- Text like [MASKED:...] is redacted; never put it into a value.
- Questions are not claims. Greetings and chit-chat are not claims."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "passage": {"type": "integer"},
                    "ctype": {"type": "string", "enum": list(CLAIM_TYPES)},
                    "subject": {"type": "string"},
                    "attribute": {"type": "string"},
                    "value": {"type": "string"},
                    "statement": {"type": "string"},
                    "modality": {"type": "string", "enum": ["decision", "proposal", "fact", "tacit"]},
                    "quote": {"type": "string"},
                },
                "required": ["passage", "ctype", "subject", "attribute", "value", "statement", "modality", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Keys pasted into hosting dashboards often carry a trailing newline or space,
        # which makes every request fail with APIConnectionError. Strip it.
        key = (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None
        _client = anthropic.Anthropic(api_key=key, timeout=LLM_TIMEOUT_S, max_retries=2)
    return _client


def _call(prompt: str) -> dict:
    kwargs = dict(
        model=LLM_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        # Server-side refusal fallback, routed by refusal category.
        resp = client().beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except (TypeError, anthropic.BadRequestError):
        resp = client().messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("Model declined to extract from this source.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


def extract(source, passages, people: dict[str, str]) -> list[Candidate]:
    out: list[Candidate] = []
    batch_size = 120
    for b in range(0, len(passages), batch_size):
        batch = passages[b:b + batch_size]
        listing = "\n".join(
            f"[{i}]{' (' + p.context + ')' if p.context else ''}{' @' + p.occurred_at if p.occurred_at else ''} {p.text}"
            for i, p in enumerate(batch)
        )
        known = ", ".join(sorted(set(people.values())))
        prompt = (f"Source file: {source.filename} (type {source.kind}).\nKnown team members: {known}.\n\n"
                  f"Passages (index in brackets):\n{listing}\n\nExtract the claims.")
        data = _call(prompt)
        for c in data.get("claims", []):
            idx = c.get("passage")
            if not isinstance(idx, int) or not 0 <= idx < len(batch):
                continue
            p = batch[idx]
            quote = c.get("quote", "")
            pos = p.text.find(quote) if quote else -1
            if pos < 0:
                # Keep it so the verifier can count and report the rejection.
                start, end, anchored = p.start, p.start, False
            else:
                start, end, anchored = p.start + pos, p.start + pos + len(quote), True
            ctype = c["ctype"]
            attr = normalize_key(c.get("attribute") or c.get("subject", ""))
            if ctype in ("owner", "deadline", "task", "contact", "status", "risk") and not attr.startswith(ctype):
                attr = f"{ctype}: {normalize_key(c.get('subject', ''))}"
            if ctype == "dependency":
                attr = f"dependency: {normalize_key(c['subject'])} -> {normalize_key(c['value'])}"
            if c.get("modality") == "proposal":
                attr = "proposal: " + normalize_key(c.get("subject", ""))
            cand = Candidate(ctype, c["subject"].strip(), attr, c["value"].strip(), c["statement"].strip(), p.id,
                             start, end, modality=c.get("modality", "fact"), occurred_at=p.occurred_at,
                             confidence=0.8, origin="llm", extra={"anchored": anchored, "quote": quote})
            out.append(cand)
    return out
