"""Stages 04-05 - Review gate, immutable versions and role-filtered recipient views.

No unapproved content can be released: recipient endpoints only ever read approved
snapshots, and every response is filtered server-side for the caller's role."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from . import readiness
from .ledger import claim_dict, departing_name, group_states, load_claims
from .models import Case, Question, Snapshot, User, now
from .policy import can_read_label
from .extract.base import normalize_value
from .verify import verify_claim

RELEASABLE = ("accepted", "edited", "unresolved")


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def approval_gate(db: Session, case: Case) -> dict:
    claims, sources = load_claims(db, case.id)
    for c in claims:
        verify_claim(db, c, sources)  # re-check anchors and hashes at approval time
    gs = group_states(claims)
    pending = [c.id for c in claims if c.review_status == "pending"]
    open_groups = [g for g, s in gs.items() if s["state"] == "open"]
    bad_anchor = [c.id for c in claims if c.review_status in ("accepted", "edited") and not c.anchored]
    releasable = [c for c in claims if c.review_status in RELEASABLE]
    issues = []
    if pending:
        issues.append({"code": "pending_claims", "message": f"{len(pending)} claim(s) still need a review decision.", "ids": pending})
    if open_groups:
        issues.append({"code": "open_conflicts", "message": f"{len(open_groups)} conflict(s) need a winner or must be explicitly kept unresolved.", "ids": open_groups})
    if bad_anchor:
        issues.append({"code": "invalid_evidence", "message": f"{len(bad_anchor)} accepted claim(s) lost their exact source anchor.", "ids": bad_anchor})
    if not releasable:
        issues.append({"code": "empty", "message": "Nothing has been accepted yet.", "ids": []})
    last = db.query(Snapshot).filter(Snapshot.case_id == case.id).order_by(Snapshot.version.desc()).first()
    if last and releasable:
        now_set = {(c.id, c.value, c.review_status) for c in releasable}
        old_set = {(c["id"], c["value"], c["review_status"]) for c in last.content["claims"]}
        if now_set == old_set:
            issues.append({"code": "no_changes", "message": f"Nothing changed since v{last.version}.", "ids": []})
    return {"ok": not issues, "issues": issues, "counts": {
        "total": len(claims), "pending": len(pending), "accepted": sum(c.review_status == "accepted" for c in claims),
        "edited": sum(c.review_status == "edited" for c in claims), "rejected": sum(c.review_status == "rejected" for c in claims),
        "unresolved": sum(c.review_status == "unresolved" for c in claims), "open_conflicts": len(open_groups)}}


def build_snapshot(db: Session, case: Case, approver: User, note: str = "") -> Snapshot:
    claims, sources = load_claims(db, case.id)
    gs = group_states(claims)
    released = [claim_dict(c, sources) for c in claims if c.review_status in RELEASABLE]
    ev = readiness.evaluate(released, gs, departing_name(db, case))
    open_qs = db.query(Question).filter(Question.case_id == case.id, Question.status == "open").all()
    version = (db.query(Snapshot).filter(Snapshot.case_id == case.id).count()) + 1
    used_sources = {e["source_id"] for c in released for e in c["evidence"]}
    content = {
        "version": version,
        "case": {"id": case.id, "name": case.name, "project": case.project, "departing": departing_name(db, case),
                 "departure_date": case.departure_date, "description": case.description},
        "approved_by": approver.name, "approved_at": now().isoformat(), "note": note,
        "group_states": gs,
        "claims": released,
        "actions": ev["actions"], "transfers": ev["transfers"],
        "open_questions": [{"id": q.id, "kind": q.kind, "prompt": q.prompt, "label": q.label} for q in open_qs],
        "sources": [{"id": s.id, "filename": s.filename, "label": s.label, "content_hash": s.content_hash, "kind": s.kind}
                    for s in sources.values() if s.id in used_sources],
    }
    snap = Snapshot(case_id=case.id, version=version, content=content, content_hash=canonical_hash(content),
                    approved_by=approver.id, note=note)
    db.add(snap)
    case.status = "released"
    return snap


def _merge_corroborating(items: list[dict]) -> list[dict]:
    """One row per (attribute, value); corroborating claims contribute extra citations."""
    out: dict[tuple, dict] = {}
    for cl in items:
        key = (cl["attribute"], normalize_value(cl["value"]))
        if key in out:
            seen = {e["id"] for e in out[key]["evidence"]}
            out[key]["evidence"] = out[key]["evidence"] + [dict(e, claim_id=cl["id"]) for e in cl["evidence"] if e["id"] not in seen]
        else:
            out[key] = dict(cl, evidence=[dict(e, claim_id=cl["id"]) for e in cl["evidence"]])
    return list(out.values())


def recipient_view(snap: Snapshot, role: str, viewer_name: str = "") -> dict:
    """Deny-by-default projection of an approved snapshot for one role."""
    c = snap.content
    readable_sources = {s["id"] for s in c["sources"] if can_read_label(role, s["label"])}

    def claim_ok(cl: dict) -> bool:
        return role in cl.get("allowed_roles", []) and all(e["source_id"] in readable_sources for e in cl["evidence"])

    visible = [cl for cl in c["claims"] if claim_ok(cl)]
    # An unresolved conflict is shown only if every side of it is visible.
    by_group: dict[str, list[dict]] = {}
    for cl in c["claims"]:
        if cl.get("conflict_group"):
            by_group.setdefault(cl["conflict_group"], []).append(cl)
    hidden_ids = set()
    for gid, members in by_group.items():
        if not all(claim_ok(m) for m in members):
            hidden_ids |= {m["id"] for m in members}
    visible = [cl for cl in visible if cl["id"] not in hidden_ids]
    vis_ids = {cl["id"] for cl in visible}

    def strip(cl: dict) -> dict:
        out = {k: v for k, v in cl.items() if k not in ("allowed_roles",)}
        return out

    actions = []
    for a in c["actions"]:
        if role in a["allowed_roles"] and all(cid in vis_ids for cid in a["claim_ids"]):
            a2 = {k: v for k, v in a.items() if k not in ("allowed_roles",)}
            a2["risk_ids"] = [r for r in a["risk_ids"] if r in vis_ids]
            a2["mine"] = bool(viewer_name and a.get("owner") == viewer_name)
            actions.append(a2)
    # The viewer's own ready work first, then everything else in readiness order.
    actions.sort(key=lambda a: (a["readiness"] != "ready", a["readiness"] == "ready" and not a["mine"]))
    for i, a in enumerate(actions):
        a["rank"] = i + 1
    transfers = [{k: v for k, v in t.items() if k != "allowed_roles"} for t in c["transfers"]
                 if role in t.get("allowed_roles", []) and t["claim_id"] in vis_ids]
    unresolved = []
    seen = set()
    for cl in visible:
        gid = cl.get("conflict_group")
        if gid and c["group_states"].get(gid, {}).get("state") != "resolved" and gid not in seen:
            seen.add(gid)
            members = [strip(m) for m in by_group[gid]]
            unresolved.append({"group": gid, "attribute": cl["attribute"], "claims": members})
    # Only the winning side of a resolved conflict is shown as a decision.
    decisions = [strip(cl) for cl in visible if cl["ctype"] in ("decision",) and cl.get("modality") != "proposal"
                 and not (cl.get("conflict_group") and c["group_states"].get(cl["conflict_group"], {}).get("state") != "resolved")]
    view = {
        "version": c["version"], "snapshot_id": snap.id, "snapshot_hash": snap.content_hash, "role": role,
        "case": c["case"], "approved_by": c["approved_by"], "approved_at": c["approved_at"], "note": c.get("note", ""),
        "viewer": viewer_name,
        "first_action": next((a for a in actions if a["readiness"] == "ready" and a.get("mine")), None)
                        or next((a for a in actions if a["readiness"] == "ready"), None),
        "actions": actions, "transfers": transfers, "decisions": _merge_corroborating(decisions),
        "proposals": [strip(cl) for cl in visible if cl.get("modality") == "proposal"],
        "owners": _merge_corroborating([strip(cl) for cl in visible if cl["ctype"] == "owner" and cl["review_status"] != "unresolved"]),
        "risks": [strip(cl) for cl in visible if cl["ctype"] in ("risk", "note")],
        "contacts": _merge_corroborating([strip(cl) for cl in visible if cl["ctype"] == "contact"]),
        "unresolved": unresolved,
        "claims": [strip(cl) for cl in visible],
        "timeline": readiness.timeline(visible),
        "open_questions": [{k: v for k, v in q.items() if k != "label"} for q in c["open_questions"] if can_read_label(role, q["label"])],
        "sources": [s for s in c["sources"] if s["id"] in readable_sources],
    }
    view["stats"] = {
        "claims": len(view["claims"]), "actions": len(actions),
        "ready": sum(a["readiness"] == "ready" for a in actions),
        "blocked": sum(a["readiness"] in ("blocked", "needs_owner", "reassign") for a in actions),
        "unresolved": len(unresolved),
    }
    view["view_hash"] = canonical_hash({k: v for k, v in view.items() if k != "view_hash"})
    return view
