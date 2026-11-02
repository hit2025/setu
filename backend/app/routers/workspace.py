"""Reviewer / departing-member workspace: cases, sources, reconstruction, ledger,
review, gap questions, approval and audit."""
from __future__ import annotations

import json
import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..auth import current_user, require
from ..config import DEMO_DIR, MAX_FILE_BYTES, MAX_FILES_PER_CASE
from ..db import get_db
from ..extract import describe as extractor_info
from ..extract.base import normalize_key, normalize_value
from ..ingest import IngestError, canonicalize, sha256
from ..ledger import claim_dict, live_state, load_claims, sync_questions
from ..models import AuditEvent, Case, Claim, Evidence, Job, Passage, Question, Receipt, Snapshot, Source, User, now
from ..policy import LABELS, can_read_label, role_matrix
from ..snapshot import approval_gate, build_snapshot
from ..verify import reconcile, support_level, verify_claim

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers
def _case_or_404(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


def _assert_case_access(case: Case, user: User, write: bool = False) -> None:
    if user.role == "reviewer":
        return
    if user.role == "departing" and case.departing_user_id == user.id and not write:
        return
    raise HTTPException(403, "You do not have access to this case workspace")


def create_source(db: Session, case: Case, filename: str, raw: bytes, label: str, user: User) -> tuple[Source | None, str]:
    if label not in LABELS:
        raise HTTPException(400, f"Unknown label '{label}'")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, f"'{filename}' exceeds {MAX_FILE_BYTES // 1_000_000} MB")
    try:
        doc = canonicalize(filename, raw)
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    dup = db.query(Source).filter(Source.case_id == case.id, Source.raw_hash == doc.raw_hash).first()
    if dup:
        return None, f"'{filename}' is identical to '{dup.filename}' (same content hash); skipped."
    src = Source(case_id=case.id, filename=filename, kind=doc.kind, label=label, raw_hash=doc.raw_hash,
                 content_hash=doc.content_hash, content=doc.content, char_count=len(doc.content), masked=doc.masked,
                 authored_at=doc.authored_at, uploaded_by=user.id)
    db.add(src)
    db.flush()
    for p in doc.passages:
        db.add(Passage(id=f"{src.id}:p{p.idx}", source_id=src.id, idx=p.idx, start=p.start, end=p.end, text=p.text,
                       context=p.context[:200], occurred_at=p.occurred_at))
    audit.log(db, case.id, user.id, "source_uploaded", {"filename": filename, "label": label, "hash": doc.content_hash[:16],
                                                       "masked": doc.masked})
    return src, ""


def source_dict(s: Source, full: bool = False) -> dict:
    d = {"id": s.id, "filename": s.filename, "kind": s.kind, "label": s.label, "raw_hash": s.raw_hash,
         "content_hash": s.content_hash, "char_count": s.char_count, "masked": s.masked or {},
         "authored_at": s.authored_at, "uploaded_by": s.uploaded_by, "uploaded_at": s.uploaded_at.isoformat(),
         "extracted": s.extracted, "excluded_reason": s.excluded_reason}
    if full:
        d["content"] = s.content
    return d


def _stage(case: Case, n_sources: int, n_claims: int, pending: int, n_snaps: int) -> int:
    if n_snaps:
        return 5
    if n_claims and pending == 0:
        return 4
    if n_claims:
        return 3
    if n_sources:
        return 2
    return 1


def case_summary(db: Session, case: Case, user: User) -> dict:
    claims = db.query(Claim).filter(Claim.case_id == case.id).all()
    n_sources = db.query(Source).filter(Source.case_id == case.id, Source.kind != "testimony").count()
    snaps = db.query(Snapshot).filter(Snapshot.case_id == case.id).order_by(Snapshot.version.desc()).all()
    qs = db.query(Question).filter(Question.case_id == case.id, Question.status == "open").all()
    pending = sum(c.review_status == "pending" for c in claims)
    departing = db.get(User, case.departing_user_id)
    reviewer = db.get(User, case.reviewer_id)
    job = db.query(Job).filter(Job.case_id == case.id).order_by(Job.created_at.desc()).first()
    acks = db.query(Receipt).filter(Receipt.case_id == case.id).all()
    my_ack = next((r for r in acks if r.user_id == user.id and snaps and r.version == snaps[0].version), None)
    return {
        "id": case.id, "name": case.name, "project": case.project, "description": case.description,
        "status": case.status, "departure_date": case.departure_date, "recipient_roles": case.recipient_roles,
        "departing": {"id": departing.id, "name": departing.name} if departing else None,
        "reviewer": {"id": reviewer.id, "name": reviewer.name} if reviewer else None,
        "created_at": case.created_at.isoformat(), "extractor_used": case.extractor_used,
        "stage": _stage(case, n_sources, len(claims), pending, len(snaps)),
        "counts": {
            "sources": n_sources, "claims": len(claims), "pending": pending,
            "accepted": sum(c.review_status in ("accepted", "edited") for c in claims),
            "rejected": sum(c.review_status == "rejected" for c in claims),
            "conflicts": len({c.conflict_group for c in claims if c.conflict_group}),
            "open_questions": len(qs) if user.role != "departing" else sum(q.target == "departing" for q in qs),
            "versions": len(snaps), "receipts": len(acks),
        },
        "latest_version": snaps[0].version if snaps else None,
        "acknowledged": bool(my_ack),
        "job": {"id": job.id, "status": job.status, "progress": job.progress, "message": job.message} if job else None,
    }


# ---------------------------------------------------------------- system
@router.get("/system")
def system_info():
    return {"extractor": extractor_info(), "labels": role_matrix(), "today": date.today().isoformat(),
            "build": os.getenv("RENDER_GIT_COMMIT", "")[:7]}


# ---------------------------------------------------------------- cases
class CaseIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    project: str = Field(min_length=2, max_length=200)
    description: str = ""
    departing_user_id: str = "rohan"
    departure_date: str = ""
    recipient_roles: list[str] = ["engineer", "coordinator"]


@router.get("/cases")
def list_cases(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.query(Case).order_by(Case.created_at.desc())
    cases = q.all()
    out = []
    for c in cases:
        if user.role == "reviewer" or (user.role == "departing" and c.departing_user_id == user.id):
            out.append(case_summary(db, c, user))
        elif user.role in c.recipient_roles and db.query(Snapshot).filter(Snapshot.case_id == c.id).count():
            s = case_summary(db, c, user)
            s["counts"] = {"versions": s["counts"]["versions"]}  # recipients see no workspace internals
            s.pop("job", None)
            out.append(s)
    return out


@router.post("/cases")
def create_case(body: CaseIn, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    if db.get(User, body.departing_user_id) is None:
        raise HTTPException(400, "Unknown departing member")
    case = Case(name=body.name, project=body.project, description=body.description,
                departing_user_id=body.departing_user_id, reviewer_id=user.id, departure_date=body.departure_date,
                recipient_roles=[r for r in body.recipient_roles if r in ("engineer", "coordinator")] or ["engineer"])
    db.add(case)
    db.flush()
    audit.log(db, case.id, user.id, "case_created", {"name": case.name})
    db.commit()
    return case_summary(db, case, user)


@router.post("/cases/demo")
def create_demo_case(user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = Case(name="Rohan Das - backend lead handover", project="CampusConnect",
                description="Synthetic demo: CampusConnect loses its backend lead during the v1.2 release. "
                            "Contains planted contradictions, missing owners, a tacit workaround, secrets and restricted files.",
                departing_user_id="rohan", reviewer_id=user.id, departure_date="2026-11-05",
                recipient_roles=["engineer", "coordinator"])
    db.add(case)
    db.flush()
    manifest = json.loads((DEMO_DIR / "manifest.json").read_text(encoding="utf-8"))
    for fname, label in manifest.items():
        create_source(db, case, fname, (DEMO_DIR / fname).read_bytes(), label, user)
    audit.log(db, case.id, user.id, "case_created", {"name": case.name, "demo": True})
    db.commit()
    return case_summary(db, case, user)


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    if user.role in ("engineer", "coordinator"):
        if user.role not in case.recipient_roles or not db.query(Snapshot).filter(Snapshot.case_id == case.id).count():
            raise HTTPException(404, "Case not found")
        s = case_summary(db, case, user)
        s["counts"] = {"versions": s["counts"]["versions"]}
        s.pop("job", None)
        return s
    _assert_case_access(case, user)
    return case_summary(db, case, user)


@router.delete("/cases/{case_id}")
def delete_case(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    for model in (Receipt, Snapshot, Question, Job):
        db.query(model).filter(model.case_id == case_id).delete()
    for c in db.query(Claim).filter(Claim.case_id == case_id).all():
        db.delete(c)
    db.delete(case)
    db.query(AuditEvent).filter(AuditEvent.case_id == case_id).delete()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- sources
@router.get("/cases/{case_id}/sources")
def list_sources(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    _assert_case_access(case, user)
    srcs = db.query(Source).filter(Source.case_id == case_id).order_by(Source.uploaded_at).all()
    return [source_dict(s) for s in srcs if can_read_label(user.role, s.label)]


@router.post("/cases/{case_id}/sources")
async def upload_sources(case_id: str, files: list[UploadFile] = File(...), labels: str = Form("{}"),
                         default_label: str = Form("team"), user: User = Depends(require("reviewer")),
                         db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    try:
        label_map = json.loads(labels or "{}")
    except json.JSONDecodeError:
        label_map = {}
    existing = db.query(Source).filter(Source.case_id == case_id, Source.kind != "testimony").count()
    if existing + len(files) > MAX_FILES_PER_CASE:
        raise HTTPException(400, f"A case holds at most {MAX_FILES_PER_CASE} files.")
    added, notes = [], []
    for f in files:
        raw = await f.read()
        src, note = create_source(db, case, f.filename or "upload.txt", raw, label_map.get(f.filename, default_label), user)
        if src:
            added.append(source_dict(src))
        if note:
            notes.append(note)
    if case.status == "released":
        case.status = "in_review"
    db.commit()
    return {"added": added, "notes": notes}


@router.get("/sources/{source_id}")
def get_source(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(404, "Source not found")
    case = _case_or_404(db, src.case_id)
    _assert_case_access(case, user)
    if not can_read_label(user.role, src.label):
        raise HTTPException(404, "Source not found")  # do not confirm existence
    d = source_dict(src, full=True)
    d["passages"] = [{"id": p.id, "start": p.start, "end": p.end, "context": p.context}
                     for p in db.query(Passage).filter(Passage.source_id == src.id).order_by(Passage.idx).all()]
    return d


class LabelIn(BaseModel):
    label: str


@router.patch("/sources/{source_id}")
def relabel_source(source_id: str, body: LabelIn, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(404, "Source not found")
    if body.label not in LABELS:
        raise HTTPException(400, "Unknown label")
    old = src.label
    src.label = body.label
    # Access is derived from labels, so every dependent claim is re-derived immediately.
    sources = {s.id: s for s in db.query(Source).filter(Source.case_id == src.case_id).all()}
    for ev in db.query(Evidence).filter(Evidence.source_id == src.id).all():
        verify_claim(db, ev.claim, sources)
    audit.log(db, src.case_id, user.id, "source_relabelled", {"filename": src.filename, "from": old, "to": body.label})
    db.commit()
    return source_dict(src)


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(404, "Source not found")
    for ev in db.query(Evidence).filter(Evidence.source_id == src.id).all():
        db.delete(ev.claim)
    audit.log(db, src.case_id, user.id, "source_deleted", {"filename": src.filename})
    db.delete(src)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- reconstruction jobs
@router.post("/cases/{case_id}/reconstruct")
def reconstruct(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    running = db.query(Job).filter(Job.case_id == case_id, Job.status.in_(("queued", "running"))).first()
    if running:
        return {"id": running.id, "status": running.status}
    if not db.query(Source).filter(Source.case_id == case_id, Source.kind != "testimony").count():
        raise HTTPException(400, "Upload at least one source first")
    job = Job(case_id=case.id, requested_by=user.id)
    db.add(job)
    audit.log(db, case.id, user.id, "reconstruct_requested", {})
    db.commit()
    return {"id": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    _assert_case_access(_case_or_404(db, job.case_id), user)
    progress, message = job.progress, job.message
    if job.status == "running":
        from ..worker import live_progress
        live = live_progress(job.id)
        if live:
            progress, message = live
    return {"id": job.id, "status": job.status, "progress": progress, "message": message, "result": job.result}


# ---------------------------------------------------------------- ledger
@router.get("/cases/{case_id}/ledger")
def ledger(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    _assert_case_access(case, user)
    state = live_state(db, case)
    claims = [c for c in state["claims"] if user.role in c["allowed_roles"]]
    vis = {c["id"] for c in claims}
    groups = {}
    for c in claims:
        if c["conflict_group"]:
            groups.setdefault(c["conflict_group"], []).append(c["id"])
    conflicts = [{"group": g, "state": state["groups"].get(g, {}).get("state", "open"),
                  "winner": state["groups"].get(g, {}).get("winner"), "claim_ids": ids,
                  "attribute": next(c["attribute"] for c in claims if c["id"] == ids[0])}
                 for g, ids in groups.items()]
    actions = [a for a in state["eval"]["actions"] if user.role in a["allowed_roles"]]
    for a in actions:
        a["risk_ids"] = [r for r in a["risk_ids"] if r in vis]
    from ..readiness import timeline
    return {"claims": claims, "conflicts": conflicts, "actions": actions,
            "transfers": [t for t in state["eval"]["transfers"] if user.role in t["allowed_roles"]],
            "timeline": timeline([c for c in claims if c["review_status"] != "rejected"])}


class ReviewIn(BaseModel):
    decision: str  # accept | reject | edit | unresolved | reset
    value: str | None = None
    note: str = ""


def _set_review(c: Claim, status: str, user: User, note: str = "") -> None:
    c.review_status, c.reviewed_by, c.reviewed_at = status, user.id, now()
    if note:
        c.review_note = note


def _settle_group(group: list[Claim], winner: Claim, user: User) -> None:
    """Agreeing claims corroborate the reviewer's choice; disagreeing ones are superseded."""
    for other in group:
        if other.id == winner.id:
            continue
        if normalize_value(other.value) == normalize_value(winner.value):
            if other.review_status in ("pending", "unresolved"):
                _set_review(other, "accepted", user, f"Corroborates reviewer's choice '{winner.value}'")
        elif other.review_status != "rejected":
            _set_review(other, "rejected", user, f"Superseded: reviewer chose '{winner.value}'")


@router.post("/claims/{claim_id}/review")
def review_claim(claim_id: str, body: ReviewIn, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(404, "Claim not found")
    case = _case_or_404(db, claim.case_id)
    group = db.query(Claim).filter(Claim.conflict_group == claim.conflict_group).all() if claim.conflict_group else []
    d = body.decision
    if d == "accept":
        _set_review(claim, "accepted", user, body.note)
        _settle_group(group, claim, user)
    elif d == "edit":
        if not body.value or not body.value.strip():
            raise HTTPException(400, "Edited value required")
        if not claim.original_value:
            claim.original_value = claim.value
        claim.value = body.value.strip()
        claim.statement = claim.statement.replace(claim.original_value, claim.value) if claim.original_value in claim.statement else f"{claim.subject}: {claim.value}"
        # Re-check: an edit is only "supported" if the cited evidence actually contains it.
        claim.support = support_level(claim.value, [e.quote for e in claim.evidence if e.valid])
        note = body.note or ("Reviewer edit not found in cited evidence" if claim.support != "supported" else "")
        _set_review(claim, "edited", user, note)
        _settle_group(group, claim, user)
    elif d == "reject":
        _set_review(claim, "rejected", user, body.note)
    elif d == "unresolved":
        if not group:
            raise HTTPException(400, "Only conflicting claims can be released as unresolved")
        for other in group:
            if other.review_status != "rejected" or other.id == claim.id:
                _set_review(other, "unresolved", user, body.note or "Released as unresolved: successor must confirm")
    elif d == "reset":
        targets = group or [claim]
        for t in targets:
            t.review_status, t.review_note, t.reviewed_by, t.reviewed_at = "pending", "", "", None
            if t.original_value:
                t.value, t.original_value = t.original_value, ""
    else:
        raise HTTPException(400, "Unknown decision")
    audit.log(db, case.id, user.id, f"claim_{d}", {"claim": claim.id, "attribute": claim.attribute, "value": claim.value})
    if case.status == "released":
        case.status = "in_review"
    db.flush()
    sync_questions(db, case)
    db.commit()
    claims, sources = load_claims(db, case.id)
    return {"claim": claim_dict(claim, sources)}


@router.post("/cases/{case_id}/claims/bulk-accept")
def bulk_accept(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    n = 0
    for c in db.query(Claim).filter(Claim.case_id == case_id, Claim.review_status == "pending").all():
        if c.conflict_group or c.origin == "testimony" or c.support != "supported" or not c.anchored:
            continue
        _set_review(c, "accepted", user, "Bulk-accepted: exact anchor and full lexical support")
        n += 1
    audit.log(db, case_id, user.id, "bulk_accept", {"count": n})
    db.flush()
    sync_questions(db, case)
    db.commit()
    return {"accepted": n}


class ManualClaimIn(BaseModel):
    source_id: str
    start: int
    end: int
    ctype: str
    subject: str
    value: str
    statement: str = ""


@router.post("/cases/{case_id}/claims")
def manual_claim(case_id: str, body: ManualClaimIn, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    """Fallback path from the Round 1 plan: evidence-linked manual claim creation."""
    case = _case_or_404(db, case_id)
    src = db.get(Source, body.source_id)
    if src is None or src.case_id != case_id:
        raise HTTPException(404, "Source not found")
    if not (0 <= body.start < body.end <= len(src.content)):
        raise HTTPException(400, "Evidence span is outside the source")
    passage = (db.query(Passage).filter(Passage.source_id == src.id, Passage.start <= body.start, Passage.end >= body.start).first())
    attr = f"{body.ctype}: {normalize_key(body.subject)}" if body.ctype not in ("decision",) else normalize_key(body.subject)
    claim = Claim(case_id=case_id, ctype=body.ctype, subject=body.subject, attribute=attr, value=body.value,
                  statement=body.statement or f"{body.subject}: {body.value}", origin="manual", confidence=1.0)
    claim.evidence.append(Evidence(source_id=src.id, passage_id=passage.id if passage else f"{src.id}:manual",
                                   start=body.start, end=body.end, quote=src.content[body.start:body.end],
                                   source_hash=src.content_hash))
    db.add(claim)
    db.flush()
    verify_claim(db, claim, {src.id: src})
    _set_review(claim, "accepted", user, "Created manually by reviewer from cited evidence")
    reconcile(db, case_id)
    db.flush()
    sync_questions(db, case)
    audit.log(db, case_id, user.id, "claim_manual", {"claim": claim.id})
    db.commit()
    return {"id": claim.id}


# ---------------------------------------------------------------- gap questions
@router.get("/cases/{case_id}/questions")
def list_questions(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    _assert_case_access(case, user)
    qs = db.query(Question).filter(Question.case_id == case_id).order_by(Question.created_at).all()
    out = []
    for q in qs:
        if not can_read_label(user.role, q.label):
            continue
        if user.role == "departing" and q.target != "departing":
            continue
        out.append({"id": q.id, "kind": q.kind, "prompt": q.prompt, "target": q.target, "subject": q.subject,
                    "attribute": q.attribute, "options": q.options, "related_claims": q.related_claims, "label": q.label,
                    "status": q.status, "answer": q.answer, "answer_value": q.answer_value, "answered_by": q.answered_by,
                    "answered_at": q.answered_at.isoformat() if q.answered_at else None})
    return out


class AnswerIn(BaseModel):
    value: str = ""
    answer: str = ""


@router.post("/questions/{question_id}/answer")
def answer_question(question_id: str, body: AnswerIn, user: User = Depends(require("departing", "reviewer")),
                    db: Session = Depends(get_db)):
    """An answer becomes labelled TESTIMONY, never a verified fact: it gets its own hashed
    source, an exact anchor, and must be accepted by the reviewer before release."""
    q = db.get(Question, question_id)
    if q is None or q.status != "open":
        raise HTTPException(404, "Open question not found")
    case = _case_or_404(db, q.case_id)
    _assert_case_access(case, user)
    if user.role == "departing" and q.target != "departing":
        raise HTTPException(403, "This question is for the reviewer")
    value = (body.value or "").strip()
    text = (body.answer or "").strip()
    if q.kind in ("conflict", "missing_owner", "owner_leaving") and not value:
        raise HTTPException(400, "Please choose or enter a value")
    if not value and not text:
        raise HTTPException(400, "Answer is empty")
    answer_line = value + (f" - {text}" if text and value else text)
    header = f"Testimony from {user.name} on {now().date().isoformat()}\nQuestion: {q.prompt}\nAnswer: "
    content = header + answer_line + "\n"
    src = Source(case_id=case.id, filename=f"testimony-{q.id}.txt", kind="testimony", label=q.label,
                 raw_hash=sha256(content), content_hash=sha256(content), content=content, char_count=len(content),
                 masked={}, authored_at=now().date().isoformat(), uploaded_by=user.id, extracted=True)
    db.add(src)
    db.flush()
    start = len(header)
    pid = f"{src.id}:p0"
    db.add(Passage(id=pid, source_id=src.id, idx=0, start=start, end=start + len(answer_line), text=answer_line,
                   context="testimony", occurred_at=now().isoformat()))
    related = db.query(Claim).filter(Claim.id.in_(q.related_claims or [])).all()
    base = related[0] if related else None
    if q.kind == "conflict" and base:
        ctype, attr, subject = base.ctype, base.attribute, base.subject
    elif q.kind in ("missing_owner", "owner_leaving"):
        ctype, attr, subject = "owner", q.attribute, q.subject
    else:
        ctype, attr, subject = "note", "note: " + q.attribute, q.subject
    claim_value = value or text
    v_start = start + answer_line.find(claim_value) if claim_value in answer_line else start
    claim = Claim(case_id=case.id, ctype=ctype, subject=subject, attribute=attr, value=claim_value,
                  statement=f"{user.name} states: {subject} -> {claim_value}" if ctype != "note" else f"Knowledge note from {user.name}: {claim_value}",
                  modality="testimony", origin="testimony", occurred_at=now().isoformat(), question_id=q.id, confidence=0.6)
    claim.evidence.append(Evidence(source_id=src.id, passage_id=pid, start=v_start, end=v_start + len(claim_value),
                                   quote=content[v_start:v_start + len(claim_value)], source_hash=src.content_hash))
    db.add(claim)
    db.flush()
    verify_claim(db, claim, {src.id: src})
    q.status, q.answer, q.answer_value, q.answered_by, q.answered_at = "answered", text, value, user.id, now()
    reconcile(db, case.id)
    db.flush()
    sync_questions(db, case)
    if case.status == "released":
        case.status = "in_review"
    audit.log(db, case.id, user.id, "question_answered", {"question": q.id, "kind": q.kind, "claim": claim.id})
    db.commit()
    return {"ok": True, "claim_id": claim.id}


# ---------------------------------------------------------------- approval & versions
@router.get("/cases/{case_id}/gate")
def gate(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    result = approval_gate(db, case)
    db.commit()
    return result


class ApproveIn(BaseModel):
    note: str = ""


@router.post("/cases/{case_id}/snapshots")
def approve(case_id: str, body: ApproveIn, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    case = _case_or_404(db, case_id)
    g = approval_gate(db, case)
    if not g["ok"]:
        db.commit()
        raise HTTPException(409, {"message": "Approval gate failed", "issues": g["issues"]})
    snap = build_snapshot(db, case, user, body.note)
    db.flush()
    audit.log(db, case.id, user.id, "version_approved", {"version": snap.version, "hash": snap.content_hash})
    db.commit()
    return {"version": snap.version, "id": snap.id, "hash": snap.content_hash}


@router.get("/cases/{case_id}/snapshots")
def list_snapshots(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    snaps = db.query(Snapshot).filter(Snapshot.case_id == case_id).order_by(Snapshot.version.desc()).all()
    receipts = db.query(Receipt).filter(Receipt.case_id == case_id).all()
    out = []
    for s in snaps:
        prev = next((p for p in snaps if p.version == s.version - 1), None)
        diff = None
        if prev:
            a = {(c["attribute"], c["value"]) for c in prev.content["claims"]}
            b = {(c["attribute"], c["value"]) for c in s.content["claims"]}
            diff = {"added": len(b - a), "removed": len(a - b)}
        out.append({"id": s.id, "version": s.version, "hash": s.content_hash, "approved_by": s.approved_by,
                    "approved_at": s.approved_at.isoformat(), "note": s.note, "claims": len(s.content["claims"]),
                    "actions": len(s.content["actions"]), "diff": diff,
                    "receipts": [{"user_id": r.user_id, "role": r.role, "at": r.acknowledged_at.isoformat(), "view_hash": r.view_hash}
                                 for r in receipts if r.snapshot_id == s.id]})
    return out


@router.get("/cases/{case_id}/audit")
def audit_log(case_id: str, user: User = Depends(require("reviewer")), db: Session = Depends(get_db)):
    events = db.query(AuditEvent).filter(AuditEvent.case_id == case_id).order_by(AuditEvent.id.desc()).limit(300).all()
    return [{"id": e.id, "actor": e.actor, "action": e.action, "detail": e.detail, "at": e.at.isoformat()} for e in events]
