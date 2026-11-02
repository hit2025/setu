"""Serialisation of the live claim ledger plus derived state (conflicts, readiness, questions)."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session, selectinload

from . import readiness
from .models import Case, Claim, Question, Source, User, now
from .verify import group_state

TASK_ID_RE = re.compile(r"^[a-z]{1,6}-\d+$")


def claim_dict(c: Claim, sources: dict[str, Source]) -> dict:
    key = c.attribute[len("task: "):] if c.attribute.startswith("task: ") else ""
    return {
        "id": c.id, "ctype": c.ctype, "subject": c.subject, "attribute": c.attribute, "value": c.value,
        "statement": c.statement, "modality": c.modality, "occurred_at": c.occurred_at, "origin": c.origin,
        "support": c.support, "anchored": c.anchored, "conflict_group": c.conflict_group,
        "review_status": c.review_status, "review_note": c.review_note, "original_value": c.original_value,
        "reviewed_by": c.reviewed_by, "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "allowed_roles": c.allowed_roles or ["reviewer"], "labels": c.labels or [], "confidence": c.confidence,
        "task_id": key.upper() if TASK_ID_RE.match(key) else None, "question_id": c.question_id,
        "evidence": [
            {"id": e.id, "source_id": e.source_id, "source_name": sources[e.source_id].filename if e.source_id in sources else "?",
             "source_label": sources[e.source_id].label if e.source_id in sources else "?",
             "passage_id": e.passage_id, "start": e.start, "end": e.end, "quote": e.quote,
             "source_hash": e.source_hash, "valid": e.valid}
            for e in c.evidence
        ],
    }


def load_claims(db: Session, case_id: str) -> tuple[list[Claim], dict[str, Source]]:
    sources = {s.id: s for s in db.query(Source).filter(Source.case_id == case_id).all()}
    claims = (db.query(Claim).options(selectinload(Claim.evidence))
              .filter(Claim.case_id == case_id).order_by(Claim.created_at, Claim.id).all())
    return claims, sources


def group_states(claims: list[Claim]) -> dict[str, dict]:
    groups: dict[str, list[Claim]] = {}
    for c in claims:
        if c.conflict_group:
            groups.setdefault(c.conflict_group, []).append(c)
    return {gid: group_state(ms) for gid, ms in groups.items()}


def departing_name(db: Session, case: Case) -> str:
    u = db.get(User, case.departing_user_id)
    return u.name if u else ""


def live_state(db: Session, case: Case) -> dict:
    claims, sources = load_claims(db, case.id)
    gs = group_states(claims)
    dicts = [claim_dict(c, sources) for c in claims]
    active = [d for d in dicts if d["review_status"] != "rejected"]
    ev = readiness.evaluate(active, gs, departing_name(db, case))
    return {"claims": dicts, "groups": gs, "eval": ev, "sources": sources}


def sync_questions(db: Session, case: Case) -> dict:
    state = live_state(db, case)
    specs = {q["key"]: q for q in state["eval"]["questions"]}
    existing = {q.key: q for q in db.query(Question).filter(Question.case_id == case.id).all()}
    created = closed = 0
    for key, spec in specs.items():
        q = existing.get(key)
        if q is None:
            target = "departing" if spec["label"] in ("public", "team", "engineering") else "reviewer"
            db.add(Question(case_id=case.id, key=key, kind=spec["kind"], prompt=spec["prompt"], target=target,
                            subject=spec["subject"], attribute=spec["attribute"], options=spec.get("options", []),
                            related_claims=spec["related"], label=spec["label"]))
            created += 1
        elif q.status == "closed" and not q.answer:
            q.status, q.prompt, q.related_claims = "open", spec["prompt"], spec["related"]
        elif q.status == "open":
            q.prompt, q.related_claims, q.options = spec["prompt"], spec["related"], spec.get("options", [])
    for key, q in existing.items():
        if key not in specs and q.status == "open":
            q.status = "closed"
            q.answered_at = now()
            closed += 1
    db.flush()
    return {"created": created, "closed": closed}
