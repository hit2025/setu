"""Stage 02 - Reconstruct. Extraction -> task linking -> dedupe -> anchoring -> support ->
access derivation -> conflict reconciliation -> question sync. Review decisions survive
re-runs: a claim with the same fingerprint keeps its reviewer decision."""
from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from . import audit
from .config import MAX_CHARS_PER_CASE
from .extract import extract_source
from .extract.base import Candidate, containment, normalize_key, normalize_value
from .ledger import sync_questions
from .models import Case, Claim, Evidence, Passage, Source, User, now
from .policy import NON_EXTRACTABLE
from .verify import reconcile, verify_claim

log = logging.getLogger("setu.pipeline")


def people_directory(db: Session) -> dict[str, str]:
    out = {}
    for u in db.query(User).all():
        out[u.id.lower()] = u.name
        out[u.name.split()[0].lower()] = u.name
        out[u.name.lower()] = u.name
    return out


def _fingerprint(ctype: str, attribute: str, value: str, source_id: str, quote: str) -> str:
    return f"{ctype}|{attribute}|{normalize_value(value)}|{source_id}|{quote.strip()[:120]}"


def link_tasks(cands: list[tuple[Candidate, Source]]) -> None:
    """Map free-text tasks onto canonical task IDs from structured exports."""
    registry: dict[str, str] = {}
    for c, _ in cands:
        if c.ctype == "task" and c.extra.get("task_id"):
            registry[c.attribute[len("task: "):]] = c.subject.split(" ", 1)[1] if " " in c.subject else c.subject
    if not registry:
        return

    def best(text: str) -> str | None:
        top, score = None, 0.0
        for key, title in registry.items():
            s = min(containment(text, title), 1.0) * 0.5 + containment(title, text) * 0.5
            if s > score:
                top, score = key, s
        return top if score >= 0.75 else None

    for c, _ in cands:
        for prefix in ("task: ", "owner: ", "deadline: "):
            if c.ctype == prefix[:-2] and c.attribute.startswith(prefix):
                key = c.attribute[len(prefix):]
                if key in registry:
                    break
                tgt = best(key)
                if tgt:
                    c.attribute = prefix + tgt
                    c.subject = f"{tgt.upper()} {registry[tgt]}"
        if c.ctype == "dependency" and c.attribute.startswith("dependency: "):
            left, _, right = c.attribute[len("dependency: "):].partition(" -> ")
            if left not in registry:
                tgt = best(left)
                if tgt:
                    c.attribute = f"dependency: {tgt} -> {right}"
                    c.subject = f"{tgt.upper()} {registry[tgt]}"


def run_reconstruction(db: Session, case_id: str, progress: Callable[[int, str], None]) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise ValueError("Case not found")
    sources = db.query(Source).filter(Source.case_id == case_id).order_by(Source.uploaded_at).all()
    extractable = [s for s in sources if s.kind != "testimony" and s.label not in NON_EXTRACTABLE]
    total_chars = sum(s.char_count for s in extractable)
    if not extractable:
        raise ValueError("No extractable sources. Upload at least one non-confidential file.")
    if total_chars > MAX_CHARS_PER_CASE:
        raise ValueError(f"Corpus has {total_chars:,} characters; the per-case limit is {MAX_CHARS_PER_CASE:,}.")

    case.status = "reconstructing"
    db.flush()

    # Preserve reviewer decisions across re-runs.
    preserved: dict[str, dict] = {}
    old = db.query(Claim).filter(Claim.case_id == case_id, Claim.origin.in_(("rules", "llm"))).all()
    for c in old:
        if c.review_status != "pending" and c.evidence:
            e = c.evidence[0]
            fp = _fingerprint(c.ctype, c.attribute, c.original_value or c.value, e.source_id, e.quote)
            preserved[fp] = {"review_status": c.review_status, "review_note": c.review_note, "value": c.value,
                             "original_value": c.original_value, "reviewed_by": c.reviewed_by, "reviewed_at": c.reviewed_at}
        db.delete(c)
    db.flush()

    people = people_directory(db)
    cands: list[tuple[Candidate, Source]] = []
    extractors, warnings = set(), []
    for i, src in enumerate(extractable):
        progress(10 + int(60 * i / max(len(extractable), 1)), f"Extracting claims from {src.filename}")
        passages = db.query(Passage).filter(Passage.source_id == src.id).order_by(Passage.idx).all()
        found, name, warn = extract_source(src, passages, people)
        extractors.add(name)
        if warn:
            warnings.append(f"{src.filename}: {warn}")
        cands.extend((c, src) for c in found)
        src.extracted = True
    for s in sources:
        if s.label in NON_EXTRACTABLE:
            s.extracted = False
            s.excluded_reason = "Confidential label: excluded from extraction and release."

    progress(72, "Linking tasks across sources")
    link_tasks(cands)

    progress(78, "Anchoring evidence spans")
    merged: dict[tuple, tuple[Candidate, Source, list[tuple[Candidate, Source]]]] = {}
    rejected = 0
    for c, src in cands:
        if c.extra.get("anchored") is False or not (0 <= c.start < c.end <= len(src.content)):
            rejected += 1
            continue
        k = (c.ctype, c.attribute, normalize_value(c.value), src.label)
        if k in merged:
            merged[k][2].append((c, src))
        else:
            merged[k] = (c, src, [(c, src)])

    src_map = {s.id: s for s in sources}
    created = []
    for c, src, group in merged.values():
        claim = Claim(case_id=case_id, ctype=c.ctype, subject=c.subject[:300], attribute=c.attribute[:200], value=c.value,
                      statement=c.statement, modality=c.modality, occurred_at=c.occurred_at or src.authored_at,
                      origin=c.origin, confidence=c.confidence)
        seen = set()
        for gc, gsrc in group:
            key = (gsrc.id, gc.start, gc.end)
            if key in seen:
                continue
            seen.add(key)
            claim.evidence.append(Evidence(source_id=gsrc.id, passage_id=gc.passage_id, start=gc.start, end=gc.end,
                                           quote=gsrc.content[gc.start:gc.end], source_hash=gsrc.content_hash))
        db.add(claim)
        created.append(claim)
    db.flush()

    progress(86, "Verifying support and deriving access")
    for claim in created:
        verify_claim(db, claim, src_map)
        e = claim.evidence[0]
        fp = _fingerprint(claim.ctype, claim.attribute, claim.value, e.source_id, e.quote)
        if fp in preserved:
            p = preserved[fp]
            claim.review_status, claim.review_note = p["review_status"], p["review_note"]
            claim.value, claim.original_value = p["value"], p["original_value"]
            claim.reviewed_by, claim.reviewed_at = p["reviewed_by"], p["reviewed_at"]
    # Re-verify testimony/manual claims too (their sources could have changed).
    for claim in db.query(Claim).filter(Claim.case_id == case_id, Claim.origin.in_(("testimony", "manual"))).all():
        verify_claim(db, claim, src_map)

    progress(92, "Reconciling conflicts")
    conflicts = reconcile(db, case_id)
    db.flush()

    progress(96, "Rehearsing next actions and generating gap questions")
    qs = sync_questions(db, case)

    case.status = "in_review"
    case.extractor_used = ", ".join(sorted(extractors))
    result = {
        "claims": len(created), "candidates": len(cands), "citations_rejected": rejected,
        "conflicts": len(conflicts), "questions_created": qs["created"], "extractors": sorted(extractors),
        "warnings": warnings, "excluded_sources": [s.filename for s in sources if s.label in NON_EXTRACTABLE],
        "finished_at": now().isoformat(),
    }
    audit.log(db, case_id, "system", "reconstruct", result)
    return result
