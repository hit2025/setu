"""The Round 2 exit criterion as an automated test: import sources, inspect contradictory
evidence, expose a missing prerequisite, review, approve a version, open two correctly
filtered recipient views, acknowledge receipt."""
import json

from app.ingest import canonicalize
from app.masking import mask_text


def _ledger(client, d, who="dev"):
    return client.get(f"/api/cases/{d['case']}/ledger", headers=d[who]).json()


def test_masking_removes_secrets():
    text, counts = mask_text("db postgres://admin:S3cret@host:5432/x mail a@b.edu phone +91 98300 12345 key rzp_live_abcdef123")
    assert "S3cret" not in text and "a@b.edu" not in text and "98300" not in text and "rzp_live" not in text
    assert counts["connection_string"] == 1 and counts["email"] == 1


def test_sources_ingested_with_hashes_and_masking(client, demo):
    srcs = client.get(f"/api/cases/{demo['case']}/sources", headers=demo["dev"]).json()
    assert len(srcs) == 7
    chat = next(s for s in srcs if s["filename"] == "backend-channel-export.json")
    assert chat["masked"].get("connection_string") == 1 and len(chat["content_hash"]) == 64
    hr = next(s for s in srcs if s["label"] == "confidential")
    assert hr["extracted"] is False and "Confidential" in hr["excluded_reason"]


def test_conflicts_detected_and_not_auto_resolved(client, demo):
    led = _ledger(client, demo)
    attrs = {c["attribute"]: c for c in led["conflicts"]}
    assert "hosting platform" in attrs and "deadline: t-101" in attrs
    assert all(c["state"] == "open" for c in led["conflicts"])
    hosting = [c for c in led["claims"] if c["attribute"] == "hosting platform"]
    assert {c["value"] for c in hosting} == {"Railway", "Render"}
    assert all(c["anchored"] for c in hosting)


def test_every_claim_has_exact_anchor(client, demo):
    led = _ledger(client, demo)
    srcs = {s["id"]: client.get(f"/api/sources/{s['id']}", headers=demo["dev"]).json()
            for s in client.get(f"/api/cases/{demo['case']}/sources", headers=demo["dev"]).json()}
    for c in led["claims"]:
        for e in c["evidence"]:
            assert srcs[e["source_id"]]["content"][e["start"]:e["end"]] == e["quote"]


def test_readiness_blocks_deploy(client, demo):
    led = _ledger(client, demo)
    deploy = next(a for a in led["actions"] if a["key"] == "t-101")
    assert deploy["readiness"] == "blocked"
    text = " ".join(deploy["blockers"])
    assert "Hosting platform" in text and "Run migration 014" in text
    t103 = next(a for a in led["actions"] if a["key"] == "t-103")
    assert t103["readiness"] == "needs_owner"
    t102 = next(a for a in led["actions"] if a["key"] == "t-102")
    assert t102["readiness"] == "reassign"


def test_departing_answers_become_testimony_not_fact(client, demo):
    qs = client.get(f"/api/cases/{demo['case']}/questions", headers=demo["rohan"]).json()
    kinds = {q["kind"] for q in qs}
    assert {"conflict", "missing_owner", "owner_leaving", "tacit"} <= kinds
    q = next(q for q in qs if q["kind"] == "missing_owner" and "Rotate Razorpay" in q["subject"])
    r = client.post(f"/api/questions/{q['id']}/answer", headers=demo["rohan"],
                    json={"value": "Meera Iyer", "answer": "Keys are in the finance vault; Dev must approve."})
    assert r.status_code == 200
    led = _ledger(client, demo)
    t = next(c for c in led["claims"] if c["id"] == r.json()["claim_id"])
    assert t["origin"] == "testimony" and t["review_status"] == "pending" and t["anchored"]
    # Still needs an owner until the reviewer verifies the testimony.
    t103 = next(a for a in led["actions"] if a["key"] == "t-103")
    assert t103["readiness"] == "needs_owner" or t103["owner"] == "Meera Iyer"
    # Rohan cannot review.
    assert client.post(f"/api/claims/{t['id']}/review", headers=demo["rohan"], json={"decision": "accept"}).status_code == 403
    client.post(f"/api/claims/{t['id']}/review", headers=demo["dev"], json={"decision": "accept"})
    t103 = next(a for a in _ledger(client, demo)["actions"] if a["key"] == "t-103")
    assert t103["owner"] == "Meera Iyer"


def test_gate_blocks_until_reviewed_then_approves(client, demo):
    d = demo
    r = client.post(f"/api/cases/{d['case']}/snapshots", headers=d["dev"], json={})
    assert r.status_code == 409
    client.post(f"/api/cases/{d['case']}/claims/bulk-accept", headers=d["dev"])
    led = _ledger(client, d)
    # Resolve hosting -> Render, keep the deadline conflict open on purpose.
    render = next(c for c in led["claims"] if c["attribute"] == "hosting platform" and c["value"] == "Render")
    client.post(f"/api/claims/{render['id']}/review", headers=d["dev"], json={"decision": "accept", "note": "Confirmed with team"})
    dl = next(c for c in led["claims"] if c["attribute"] == "deadline: t-101")
    client.post(f"/api/claims/{dl['id']}/review", headers=d["dev"], json={"decision": "unresolved"})
    for c in _ledger(client, d)["claims"]:
        if c["review_status"] == "pending":
            client.post(f"/api/claims/{c['id']}/review", headers=d["dev"], json={"decision": "accept"})
    g = client.get(f"/api/cases/{d['case']}/gate", headers=d["dev"]).json()
    assert g["ok"], g
    r = client.post(f"/api/cases/{d['case']}/snapshots", headers=d["dev"], json={"note": "v1"})
    assert r.status_code == 200 and r.json()["version"] == 1


RESTRICTED_FOR_COORDINATOR = ["Railway free tier", "hosting platform is Render", "workaround: disable", "unique index", "S3cret", "ByteForge", "12000", "Acme", "199 INR",
                              "backend-channel-export", "repo-activity", "budget-and-sponsors", "hr-departure",
                              "98300", "idempotent", "internship"]
RESTRICTED_FOR_ENGINEER = ["ByteForge", "12000", "Acme", "199 INR", "budget-and-sponsors", "hr-departure", "98300", "internship"]


def test_recipient_views_are_filtered(client, demo):
    d = demo
    eng = client.get(f"/api/cases/{d['case']}/handover", headers=d["meera"]).json()
    coord = client.get(f"/api/cases/{d['case']}/handover", headers=d["ananya"]).json()
    eng_s, coord_s = json.dumps(eng), json.dumps(coord)
    for needle in RESTRICTED_FOR_COORDINATOR:
        assert needle not in coord_s, f"coordinator leak: {needle}"
    for needle in RESTRICTED_FOR_ENGINEER:
        assert needle not in eng_s, f"engineer leak: {needle}"
    assert "Render" in eng_s and "workaround" in eng_s
    assert not any(c["attribute"] == "hosting platform" for c in coord["claims"])
    assert any(a["key"] == "t-107" for a in coord["actions"])
    assert not any(a["key"] == "t-101" for a in coord["actions"])
    assert eng["first_action"] is not None


def test_access_denials(client, demo):
    d = demo
    case = d["case"]
    # Recipients cannot open the workspace, the ledger, sources or other roles' views.
    assert client.get(f"/api/cases/{case}/ledger", headers=d["ananya"]).status_code == 403
    assert client.get(f"/api/cases/{case}/handover?as_role=engineer", headers=d["ananya"]).status_code == 403
    srcs = client.get(f"/api/cases/{case}/sources", headers=d["dev"]).json()
    fin = next(s for s in srcs if s["label"] == "finance")
    assert client.get(f"/api/sources/{fin['id']}", headers=d["rohan"]).status_code == 404
    assert client.get(f"/api/sources/{fin['id']}", headers=d["meera"]).status_code == 403
    # Departing member never sees finance/confidential sources in the list.
    labels = {s["label"] for s in client.get(f"/api/cases/{case}/sources", headers=d["rohan"]).json()}
    assert labels <= {"team", "engineering", "public"}
    # No token -> 401.
    assert client.get(f"/api/cases/{case}/handover").status_code == 401
    # Tampered token -> 401.
    bad = {"Authorization": d["meera"]["Authorization"][:-3] + "abc"}
    assert client.get("/api/auth/me", headers=bad).status_code == 401


def test_citation_rechecks_access(client, demo):
    d = demo
    eng = client.get(f"/api/cases/{d['case']}/handover", headers=d["meera"]).json()
    c = next(c for c in eng["claims"] if c["value"] == "Render")
    r = client.get(f"/api/cases/{d['case']}/handover/citation",
                   params={"claim_id": c["id"], "evidence_id": c["evidence"][0]["id"]}, headers=d["meera"])
    assert r.status_code == 200 and r.json()["intact"] and "Render" in r.json()["quote"]
    # Same citation id requested by the coordinator is indistinguishable from a missing one.
    r = client.get(f"/api/cases/{d['case']}/handover/citation",
                   params={"claim_id": c["id"], "evidence_id": c["evidence"][0]["id"]}, headers=d["ananya"])
    assert r.status_code == 404
    hits = client.get(f"/api/cases/{d['case']}/handover/search", params={"q": "hosting platform"}, headers=d["ananya"]).json()
    assert all(h["claim"]["attribute"] != "hosting platform" for h in hits)
    hits = client.get(f"/api/cases/{d['case']}/handover/search", params={"q": "hosting platform"}, headers=d["meera"]).json()
    assert any(h["claim"]["value"] == "Render" for h in hits)


def test_acknowledgement_binds_version(client, demo):
    d = demo
    r = client.post(f"/api/cases/{d['case']}/handover/ack", headers=d["meera"], json={"version": 1})
    assert r.status_code == 200 and len(r.json()["view_hash"]) == 64
    snaps = client.get(f"/api/cases/{d['case']}/snapshots", headers=d["dev"]).json()
    assert snaps[0]["receipts"][0]["user_id"] == "meera"
    assert client.post(f"/api/cases/{d['case']}/handover/ack", headers=d["dev"], json={"version": 1}).status_code == 403


def test_canonicalize_rejects_bad_json():
    import pytest
    from app.ingest import IngestError
    with pytest.raises(IngestError):
        canonicalize("x.json", b"{not json")
