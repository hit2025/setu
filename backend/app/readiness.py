"""Action-readiness rehearsal.

Before anything is handed over, every next action is checked for: an owner who is staying,
a deadline, evidence, and direct prerequisites (other tasks, decisions, PRs) that are
actually satisfied. Missing or conflicting information BLOCKS the action instead of being
smoothed into confident prose. Works on plain dicts so it runs identically on the live
ledger and on frozen snapshots."""
from __future__ import annotations

from .extract.base import containment, normalize_key, normalize_value, token_set
from .policy import ROLES

DONE = {"done", "closed", "merged", "complete", "completed", "resolved", "released"}
LABEL_ORDER = ["public", "team", "engineering", "finance", "confidential"]


def _intersect(roles_lists: list[list[str]]) -> list[str]:
    allowed = set(ROLES)
    for r in roles_lists:
        allowed &= set(r)
    allowed.add("reviewer")
    return sorted(allowed)


def strictest_label(labels) -> str:
    labels = [l for l in labels if l in LABEL_ORDER] or ["team"]
    return max(labels, key=LABEL_ORDER.index)


def _is_person(value: str, name: str) -> bool:
    if not name:
        return False
    v, n = value.strip().lower(), name.strip().lower()
    return v == n or v == n.split()[0] or v.split()[0] == n.split()[0] and len(v.split()) == 1


def _source_names(claim: dict) -> str:
    return ", ".join(sorted({e.get("source_name", "?") for e in claim.get("evidence", [])}))


def evaluate(claims: list[dict], group_states: dict[str, dict], departing_name: str) -> dict:
    """claims: non-rejected claims as dicts. Returns actions, transfers, question specs."""
    by_attr: dict[str, list[dict]] = {}
    for c in claims:
        by_attr.setdefault(c["attribute"], []).append(c)

    def effective(attr: str) -> tuple[str, str | None, list[dict], str]:
        """-> (state, value, claims, detail) where state in ok|conflict|kept_open|missing."""
        cs = [c for c in by_attr.get(attr, []) if c.get("modality") != "proposal"]
        if not cs:
            return "missing", None, [], ""
        gid = next((c["conflict_group"] for c in cs if c.get("conflict_group")), None)
        if gid:
            st = group_states.get(gid, {"state": "open"})
            if st["state"] == "resolved":
                win = next((c for c in cs if c["id"] == st["winner"]), cs[0])
                return "ok", win["value"], [win], ""
            detail = " vs ".join(f"{c['value']} ({_source_names(c)})" for c in cs)
            return ("kept_open" if st["state"] == "kept_open" else "conflict"), None, cs, detail
        return "ok", cs[0]["value"], cs, ""

    tasks: dict[str, list[dict]] = {}
    for c in claims:
        if c["ctype"] == "task":
            tasks.setdefault(c["attribute"][len("task: "):], []).append(c)
    titles = {}
    for key, cs in tasks.items():
        primary = next((c for c in cs if c.get("task_id")), cs[0])
        titles[key] = primary["subject"]

    decisions = {c["attribute"] for c in claims if c["ctype"] == "decision" and c.get("modality") != "proposal"}
    statuses = {c["attribute"][len("status: "):]: c for c in claims if c["ctype"] == "status"}
    risks = [c for c in claims if c["ctype"] in ("risk", "note")]

    def task_status(key: str) -> tuple[str, list[dict]]:
        cs = tasks.get(key, [])
        explicit = [c for c in cs if normalize_value(c["value"]) not in ("open", "")]
        pick = explicit[0] if explicit else (cs[0] if cs else None)
        return (normalize_value(pick["value"]) if pick else "open"), cs

    def resolve_prereq(value: str) -> dict:
        nk = normalize_key(value)
        if nk in tasks:
            return {"kind": "task", "ref": nk}
        best, score = None, 0.0
        for key, title in titles.items():
            s = containment(value, title)
            if s > score:
                best, score = key, s
        if best and score >= 0.6:
            return {"kind": "task", "ref": best}
        for attr in decisions:
            if nk == attr or containment(value, attr) >= 0.8 and containment(attr, value) >= 0.5:
                return {"kind": "decision", "ref": attr}
        for ref in statuses:
            if nk == ref or containment(value, ref) >= 0.99:
                return {"kind": "status", "ref": ref}
        return {"kind": "unknown", "ref": nk}

    actions, questions = [], []
    for key, tcs in tasks.items():
        title = titles[key]
        status, _ = task_status(key)
        used = list(tcs)
        checks, blockers = [], []

        # Owner
        o_state, owner, o_claims, o_detail = effective(f"owner: {key}")
        used += o_claims
        if o_state == "missing":
            checks.append({"check": "owner", "ok": False, "detail": "No owner named in any source"})
        elif o_state in ("conflict", "kept_open"):
            checks.append({"check": "owner", "ok": False, "detail": f"Ownership disputed: {o_detail}"})
            owner = None
        elif _is_person(owner, departing_name):
            checks.append({"check": "owner", "ok": False, "detail": f"Owner {owner} is the departing member"})
        else:
            checks.append({"check": "owner", "ok": True, "detail": owner})

        # Deadline
        d_state, due, d_claims, d_detail = effective(f"deadline: {key}")
        used += d_claims
        checks.append({"check": "deadline", "ok": d_state == "ok",
                       "detail": due if d_state == "ok" else (f"Disputed: {d_detail}" if d_detail else "No due date")})

        # Evidence quality
        weak = [c for c in tcs if c.get("support") != "supported" or not c.get("anchored", True)]
        checks.append({"check": "evidence", "ok": not weak,
                       "detail": "Exact source anchors verified" if not weak else "Weak or invalid evidence"})

        # Prerequisites (direct)
        prereqs = []
        dep_claims = [c for c in claims if c["ctype"] == "dependency" and c["attribute"].startswith(f"dependency: {key} ->")]
        seen = set()
        for dc in dep_claims:
            target = resolve_prereq(dc["value"])
            tkey = (target["kind"], target["ref"])
            if tkey in seen:
                # Corroborating evidence for the same prerequisite.
                used.append(dc)
                continue
            seen.add(tkey)
            used.append(dc)
            pr = {"label": dc["value"], "kind": target["kind"], "ref": target["ref"], "claim_id": dc["id"]}
            if target["kind"] == "task":
                st, pcs = task_status(target["ref"])
                used += pcs
                pr["label"] = titles[target["ref"]]
                pr["ok"] = st in DONE
                pr["detail"] = f"{st.replace('_', ' ')}"
            elif target["kind"] == "decision":
                st, val, dcs, det = effective(target["ref"])
                used += dcs
                pr["label"] = target["ref"].capitalize()
                pr["ok"] = st == "ok"
                pr["detail"] = f"Decided: {val}" if st == "ok" else (
                    f"Unresolved conflict: {det}" if st == "conflict" else f"Reviewer marked unresolved: {det}")
            elif target["kind"] == "status":
                sc = statuses[target["ref"]]
                used.append(sc)
                pr["ok"] = normalize_value(sc["value"]) in DONE
                pr["detail"] = sc["value"]
            else:
                pr["ok"] = False
                pr["detail"] = "No source explains this prerequisite"
            prereqs.append(pr)
            if not pr["ok"]:
                blockers.append(f"{pr['label']}: {pr['detail']}")
        checks.append({"check": "prerequisites", "ok": not blockers,
                       "detail": f"{len(prereqs)} direct prerequisite(s) satisfied" if not blockers else f"{len(blockers)} unmet"})

        linked_risks = []
        for r in risks:
            if containment(title, r["value"]) >= 0.6 or containment(r["subject"], title) >= 0.6 or containment(title, r["subject"]) >= 0.6:
                linked_risks.append(r["id"])

        owner_check = checks[0]
        if status in DONE:
            readiness = "done"
        elif blockers:
            readiness = "blocked"
        elif not owner_check["ok"] and "departing" in owner_check["detail"]:
            readiness = "reassign"
        elif not owner_check["ok"]:
            readiness = "needs_owner"
        else:
            readiness = "ready"

        actions.append({
            "key": key, "title": title, "status": status, "owner": owner, "due": due,
            "readiness": readiness, "checks": checks, "prerequisites": prereqs, "blockers": blockers,
            "risk_ids": linked_risks, "claim_ids": sorted({c["id"] for c in used}),
            "allowed_roles": _intersect([c.get("allowed_roles", ["reviewer"]) for c in used]),
            "labels": sorted({l for c in used for l in c.get("labels", [])}),
        })

        if readiness == "needs_owner" and o_state == "missing":
            questions.append({"key": f"missing_owner|{key}", "kind": "missing_owner", "subject": title, "attribute": f"owner: {key}",
                              "prompt": f"Nobody is named as owner of '{title}'. Who should own it after the handover?",
                              "related": [c["id"] for c in tcs], "labels": [l for c in tcs for l in c.get("labels", [])]})
        elif o_state == "ok" and owner and _is_person(owner, departing_name) and readiness != "done":
            questions.append({"key": f"owner_leaving|{key}", "kind": "owner_leaving", "subject": title, "attribute": f"owner: {key}",
                              "prompt": f"'{title}' is owned by {owner}, who is leaving. Who takes it over, and what state is it in right now?",
                              "related": [c["id"] for c in o_claims], "labels": [l for c in o_claims for l in c.get("labels", [])]})
        for pr in prereqs:
            if pr["kind"] == "unknown":
                questions.append({"key": f"unknown_prereq|{key}|{pr['ref']}", "kind": "unknown_prereq", "subject": title,
                                  "attribute": f"dependency: {key} -> {pr['ref']}",
                                  "prompt": f"'{title}' depends on '{pr['label']}', but no source explains it. What is it, and is it done?",
                                  "related": [pr["claim_id"]], "labels": [l for c in tcs for l in c.get("labels", [])]})

    order = {"ready": 0, "reassign": 1, "needs_owner": 2, "blocked": 3, "done": 4}
    actions.sort(key=lambda a: (order[a["readiness"]], a["due"] or "9999", a["title"]))
    for i, a in enumerate(actions):
        a["rank"] = i + 1

    # Conflicts anywhere in the ledger become questions too.
    seen_groups = set()
    for c in claims:
        gid = c.get("conflict_group")
        if gid and gid not in seen_groups and group_states.get(gid, {}).get("state") == "open":
            seen_groups.add(gid)
            members = [m for m in claims if m.get("conflict_group") == gid]
            if any(m.get("origin") == "testimony" for m in members):
                continue  # already answered; waiting for reviewer verification
            vals = " vs ".join(f"'{m['value']}' ({_source_names(m)})" for m in members)
            attr = c["attribute"]
            questions.append({"key": f"conflict|{attr}", "kind": "conflict", "subject": c["subject"], "attribute": attr,
                              "prompt": f"Sources disagree on {attr}: {vals}. Which is current and approved?",
                              "options": sorted({m["value"] for m in members}),
                              "related": [m["id"] for m in members], "labels": [l for m in members for l in m.get("labels", [])]})

    # Tacit knowledge: workarounds that live only in someone's head.
    for r in risks:
        if r.get("modality") == "tacit" and r.get("origin") != "testimony":
            questions.append({"key": f"tacit|{r['attribute']}", "kind": "tacit", "subject": r["subject"], "attribute": r["attribute"],
                              "prompt": f"Document this workaround so the successor can repeat it safely: \"{r['value']}\". Exact steps, and when can it be removed?",
                              "related": [r["id"]], "labels": r.get("labels", [])})

    # Areas (not tasks) owned by the departing member.
    transfers = []
    task_keys = set(tasks)
    for c in claims:
        if c["ctype"] == "owner" and c["attribute"][len("owner: "):] not in task_keys and _is_person(c["value"], departing_name):
            area = c["subject"]
            transfers.append({"area": area, "owner": c["value"], "claim_id": c["id"], "allowed_roles": c.get("allowed_roles", [])})
            questions.append({"key": f"owner_leaving|area|{c['attribute']}", "kind": "owner_leaving", "subject": area,
                              "attribute": c["attribute"],
                              "prompt": f"{c['value']} owns '{area}'. Who should take over this area?",
                              "related": [c["id"]], "labels": c.get("labels", [])})

    for q in questions:
        q["label"] = strictest_label(q.pop("labels", []))
    return {"actions": actions, "transfers": transfers, "questions": questions}


def timeline(claims: list[dict]) -> list[dict]:
    events = []
    for c in claims:
        if c["ctype"] == "deadline" and len(c["value"]) >= 10:
            events.append({"date": c["value"][:10], "kind": "deadline", "text": c["statement"], "claim_id": c["id"],
                           "conflict": bool(c.get("conflict_group"))})
        elif c.get("occurred_at") and c["ctype"] in ("decision", "status", "risk", "task"):
            events.append({"date": c["occurred_at"][:10], "kind": c["ctype"], "text": c["statement"], "claim_id": c["id"],
                           "conflict": bool(c.get("conflict_group"))})
    events.sort(key=lambda e: e["date"])
    return events
