"""Stage 03 - Verify. Deterministic gates that do not trust model output.

Gate 1  Anchor evidence   - the cited span must exist verbatim in the canonical source,
                            and the source hash must still match.
Gate 2  Reconcile state   - incompatible values for the same attribute become a visible
                            conflict group. Timestamps never silently pick a winner.
Gate 3  Validate support  - lexical check that the claim value is backed by its quote
                            (weak / unsupported claims stay labelled for the reviewer).
Gate 4  Authorise release - readers = intersection of every supporting source's readers.
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from .extract.base import normalize_value, token_set
from .ingest import sha256
from .models import Claim, Evidence, Source
from .policy import readers_for_labels

RECONCILE_TYPES = {"decision", "deadline", "owner", "contact", "status"}


def anchor_ok(ev: Evidence, src: Source) -> bool:
    if src is None or sha256(src.content) != src.content_hash or ev.source_hash != src.content_hash:
        return False
    if not (0 <= ev.start < ev.end <= len(src.content)):
        return False
    return src.content[ev.start:ev.end] == ev.quote


def support_level(value: str, quotes: list[str]) -> str:
    vt = token_set(value)
    if not vt:
        return "weak"
    best = 0.0
    for q in quotes:
        qt = token_set(q)
        best = max(best, len(vt & qt) / len(vt))
    if best >= 0.99:
        return "supported"
    if best >= 0.5:
        return "weak"
    return "unsupported"


def verify_claim(db: Session, claim: Claim, sources: dict[str, Source]) -> None:
    labels, quotes, all_ok = set(), [], bool(claim.evidence)
    for ev in claim.evidence:
        src = sources.get(ev.source_id) or db.get(Source, ev.source_id)
        ok = anchor_ok(ev, src)
        ev.valid = ok
        all_ok = all_ok and ok
        if src is not None:
            labels.add(src.label)
        if ok:
            quotes.append(ev.quote)
    claim.anchored = all_ok
    claim.labels = sorted(labels)
    claim.allowed_roles = readers_for_labels(labels)
    if not all_ok:
        claim.support = "unsupported"
    elif claim.ctype in ("risk", "note") or claim.modality == "proposal" or (
            claim.ctype == "task" and normalize_value(claim.value) == "open"):
        # Default task status: nothing to look up in the quote.
        claim.support = "supported" if quotes else "unsupported"
    else:
        claim.support = support_level(claim.value, quotes)


def reconcile(db: Session, case_id: str) -> list[dict]:
    """Recompute conflict groups. Rejected claims never participate."""
    claims = db.query(Claim).filter(Claim.case_id == case_id).all()
    for c in claims:
        c.conflict_group = None
    groups: dict[str, list[Claim]] = {}
    for c in claims:
        # Rejected claims stay in their group so a resolved conflict keeps its history.
        if c.ctype not in RECONCILE_TYPES or c.modality == "proposal":
            continue
        groups.setdefault(f"{c.ctype}|{c.attribute}", []).append(c)
    out = []
    for key, members in groups.items():
        values = {normalize_value(m.value) for m in members}
        if len(values) < 2:
            continue
        gid = "cg-" + hashlib.sha1(f"{case_id}|{key}".encode()).hexdigest()[:10]
        for m in members:
            m.conflict_group = gid
        out.append({"group": gid, "attribute": members[0].attribute, "values": sorted(values), "claims": [m.id for m in members]})
    return out


def group_state(members: list[Claim]) -> dict:
    """resolved: exactly one accepted/edited winner. kept_open: reviewer released it as unresolved."""
    live = [m for m in members if m.review_status != "rejected"]
    if not live:
        return {"state": "dropped", "winner": None}
    winners = [m for m in live if m.review_status in ("accepted", "edited")]
    # Resolved: every surviving claim was accepted and they all agree on one value.
    if winners and len(winners) == len(live) and len({normalize_value(w.value) for w in winners}) == 1:
        return {"state": "resolved", "winner": winners[0].id}
    if live and all(m.review_status == "unresolved" for m in live):
        return {"state": "kept_open", "winner": None}
    return {"state": "open", "winner": None}
