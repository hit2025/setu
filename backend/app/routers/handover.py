"""Recipient endpoints. They read ONLY approved snapshots and filter server-side per role.
Every citation open re-checks access and source integrity."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit
from ..auth import PERSONAS, current_user, issue_token
from ..db import get_db
from ..extract.base import token_set
from ..ingest import sha256
from ..models import Case, Receipt, Snapshot, Source, User
from ..policy import RECIPIENT_ROLES, can_read_label
from ..snapshot import recipient_view

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    user_id: str


@router.get("/auth/personas")
def personas():
    return PERSONAS


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(404, "Unknown persona")
    audit.log(db, None, user.id, "login", {})
    db.commit()
    return {"token": issue_token(user), "user": {"id": user.id, "name": user.name, "role": user.role, "title": user.title}}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "role": user.role, "title": user.title}


# ---------------------------------------------------------------- handover
def _viewer_name(db: Session, user: User, role: str) -> str:
    if user.role == role:
        return user.name
    persona = db.query(User).filter(User.role == role).first()  # reviewer preview
    return persona.name if persona else ""


def _resolve(db: Session, case_id: str, user: User, version: int | None, as_role: str | None) -> tuple[Case, Snapshot, str]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if user.role == "reviewer":
        role = as_role or "engineer"
        if role not in RECIPIENT_ROLES + ("reviewer", "departing"):
            raise HTTPException(400, "Unknown role")
    elif user.role in RECIPIENT_ROLES:
        if as_role and as_role != user.role:
            raise HTTPException(403, "Recipients can only open their own view")
        if user.role not in case.recipient_roles:
            raise HTTPException(404, "Case not found")
        role = user.role
    else:
        raise HTTPException(403, "The departing member does not receive the handover")
    q = db.query(Snapshot).filter(Snapshot.case_id == case_id)
    snap = (q.filter(Snapshot.version == version).first() if version else q.order_by(Snapshot.version.desc()).first())
    if snap is None:
        raise HTTPException(404, "No approved handover version exists yet")
    return case, snap, role


@router.get("/cases/{case_id}/handover")
def handover(case_id: str, version: int | None = None, as_role: str | None = None,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, snap, role = _resolve(db, case_id, user, version, as_role)
    view = recipient_view(snap, role, _viewer_name(db, user, role))
    latest = db.query(Snapshot).filter(Snapshot.case_id == case_id).order_by(Snapshot.version.desc()).first()
    view["latest_version"] = latest.version
    view["versions"] = [s.version for s in db.query(Snapshot).filter(Snapshot.case_id == case_id).order_by(Snapshot.version).all()]
    rec = db.query(Receipt).filter(Receipt.snapshot_id == snap.id, Receipt.user_id == user.id).first()
    view["receipt"] = {"at": rec.acknowledged_at.isoformat(), "view_hash": rec.view_hash} if rec else None
    view["preview"] = user.role == "reviewer"
    if user.role != "reviewer":
        audit.log(db, case_id, user.id, "handover_opened", {"version": snap.version, "role": role})
        db.commit()
    return view


@router.get("/cases/{case_id}/handover/citation")
def citation(case_id: str, claim_id: str, evidence_id: str, version: int | None = None, as_role: str | None = None,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    case, snap, role = _resolve(db, case_id, user, version, as_role)
    view = recipient_view(snap, role, _viewer_name(db, user, role))
    # The evidence may belong to a corroborating claim merged into the row the user clicked;
    # either way it must be inside this role's filtered view.
    claim = next((c for c in view["claims"] if c["id"] == claim_id), None)
    pair = next(((c, e) for c in view["claims"] for e in c["evidence"] if e["id"] == evidence_id), None)
    ev = pair[1] if pair else None
    if claim is None or ev is None:
        raise HTTPException(404, "Citation not found")  # identical response for hidden and missing
    src = db.get(Source, ev["source_id"])
    if src is None or not can_read_label(role, src.label):  # re-checked on every open, against the CURRENT label
        raise HTTPException(404, "Citation not found")
    intact = sha256(src.content) == ev["source_hash"] and src.content[ev["start"]:ev["end"]] == ev["quote"]
    a, b = max(0, ev["start"] - 240), min(len(src.content), ev["end"] + 240)
    if user.role != "reviewer":
        audit.log(db, case_id, user.id, "citation_opened", {"claim": claim_id, "source": src.filename})
        db.commit()
    return {"source": {"id": src.id, "filename": src.filename, "label": src.label, "kind": src.kind,
                       "content_hash": src.content_hash},
            "before": src.content[a:ev["start"]], "quote": src.content[ev["start"]:ev["end"]], "after": src.content[ev["end"]:b],
            "start": ev["start"], "end": ev["end"], "intact": intact,
            "claim": {"id": claim["id"], "statement": claim["statement"], "review_status": claim["review_status"]}}


@router.get("/cases/{case_id}/handover/search")
def search(case_id: str, q: str, version: int | None = None, as_role: str | None = None,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Search runs over the SAME role-filtered view, so it cannot leak restricted claims."""
    _, snap, role = _resolve(db, case_id, user, version, as_role)
    view = recipient_view(snap, role, _viewer_name(db, user, role))
    qt = token_set(q)
    if not qt:
        return []
    scored = []
    for c in view["claims"]:
        text = f"{c['statement']} {c['subject']} {c['value']}"
        st = token_set(text)
        hit = len(qt & st) / len(qt)
        if hit > 0 or q.lower() in text.lower():
            scored.append((hit + (0.5 if q.lower() in text.lower() else 0), c))
    scored.sort(key=lambda x: -x[0])
    return [{"score": round(s, 2), "claim": c} for s, c in scored[:20]]


class AckIn(BaseModel):
    version: int


@router.post("/cases/{case_id}/handover/ack")
def acknowledge(case_id: str, body: AckIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in RECIPIENT_ROLES:
        raise HTTPException(403, "Only recipients acknowledge a handover")
    case, snap, role = _resolve(db, case_id, user, body.version, None)
    view = recipient_view(snap, role, _viewer_name(db, user, role))
    existing = db.query(Receipt).filter(Receipt.snapshot_id == snap.id, Receipt.user_id == user.id).first()
    if existing:
        return {"at": existing.acknowledged_at.isoformat(), "view_hash": existing.view_hash, "version": snap.version}
    rec = Receipt(case_id=case.id, snapshot_id=snap.id, version=snap.version, user_id=user.id, role=role,
                  view_hash=view["view_hash"])
    db.add(rec)
    audit.log(db, case.id, user.id, "handover_acknowledged", {"version": snap.version, "view_hash": view["view_hash"][:16]})
    db.commit()
    return {"at": rec.acknowledged_at.isoformat(), "view_hash": rec.view_hash, "version": snap.version}
