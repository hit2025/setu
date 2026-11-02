"""Round 1 target: 0 restricted-content disclosures across >=100 adversarial access probes."""
import json

from conftest import login

RESTRICTED_TEXT = {
    "coordinator": ["Railway free tier", "hosting platform is Render", "workaround: disable", "unique index", "S3cret",
                    "ByteForge", "12000", "Acme", "199 INR", "backend-channel-export", "repo-activity",
                    "budget-and-sponsors", "hr-departure", "98300", "idempotent", "internship"],
    "engineer": ["ByteForge", "12000", "Acme", "199 INR", "budget-and-sponsors", "hr-departure", "98300", "internship", "S3cret"],
}
READ_MATRIX = {
    "reviewer": {"team", "engineering", "finance", "confidential"},
    "departing": {"team", "engineering"},
}


def _ensure_released(client, demo):
    d = demo
    if client.get(f"/api/cases/{d['case']}/snapshots", headers=d["dev"]).json():
        return
    client.post(f"/api/cases/{d['case']}/claims/bulk-accept", headers=d["dev"])
    for c in client.get(f"/api/cases/{d['case']}/ledger", headers=d["dev"]).json()["claims"]:
        if c["review_status"] == "pending":
            client.post(f"/api/claims/{c['id']}/review", headers=d["dev"],
                        json={"decision": "unresolved" if c["conflict_group"] else "accept"})
    assert client.post(f"/api/cases/{d['case']}/snapshots", headers=d["dev"], json={}).status_code == 200


def test_hundred_adversarial_probes(client, demo):
    d = demo
    _ensure_released(client, d)
    case = d["case"]
    hdr = {"reviewer": d["dev"], "departing": d["rohan"], "engineer": d["meera"], "coordinator": d["ananya"]}
    probes, failures = 0, []

    def check(name, ok):
        nonlocal probes
        probes += 1
        if not ok:
            failures.append(name)

    sources = client.get(f"/api/cases/{case}/sources", headers=d["dev"]).json()
    # 1. Direct source reads for every role x source (28).
    for role, h in hdr.items():
        for s in sources:
            r = client.get(f"/api/sources/{s['id']}", headers=h)
            allowed = s["label"] in READ_MATRIX.get(role, set())
            check(f"source {s['filename']} as {role}", (r.status_code == 200) == allowed)

    # 2. Cross-role citation replay: every engineer-visible citation requested by the coordinator.
    eng = client.get(f"/api/cases/{case}/handover", headers=d["meera"]).json()
    coord = client.get(f"/api/cases/{case}/handover", headers=d["ananya"]).json()
    coord_ids = {c["id"] for c in coord["claims"]}
    for c in eng["claims"]:
        if c["id"] in coord_ids:
            continue
        for e in c["evidence"]:
            r = client.get(f"/api/cases/{case}/handover/citation", params={"claim_id": c["id"], "evidence_id": e["id"]},
                           headers=d["ananya"])
            check(f"citation {c['id']} as coordinator", r.status_code == 404)

    # 3. Restricted text never appears in recipient views or search results.
    for role in ("engineer", "coordinator"):
        view = json.dumps(eng if role == "engineer" else coord)
        for needle in RESTRICTED_TEXT[role]:
            check(f"view leak {needle} -> {role}", needle not in view)
            hits = client.get(f"/api/cases/{case}/handover/search", params={"q": needle}, headers=hdr[role]).json()
            check(f"search leak {needle} -> {role}", needle.lower() not in json.dumps(hits).lower())

    # 4. Role impersonation through query parameters.
    check("coord as engineer", client.get(f"/api/cases/{case}/handover?as_role=engineer", headers=d["ananya"]).status_code == 403)
    check("eng as coordinator", client.get(f"/api/cases/{case}/handover?as_role=coordinator", headers=d["meera"]).status_code == 403)
    check("eng as reviewer", client.get(f"/api/cases/{case}/handover?as_role=reviewer", headers=d["meera"]).status_code == 403)
    check("departing handover", client.get(f"/api/cases/{case}/handover", headers=d["rohan"]).status_code == 403)

    # 5. Workspace endpoints are closed to recipients (and writes to the departing member).
    claim_id = eng["claims"][0]["id"]
    endpoints = [("get", f"/api/cases/{case}/ledger"), ("get", f"/api/cases/{case}/questions"),
                 ("get", f"/api/cases/{case}/gate"), ("get", f"/api/cases/{case}/snapshots"),
                 ("get", f"/api/cases/{case}/audit"), ("get", f"/api/cases/{case}/sources"),
                 ("post", f"/api/cases/{case}/reconstruct"), ("post", f"/api/cases/{case}/claims/bulk-accept"),
                 ("post", f"/api/claims/{claim_id}/review"), ("post", f"/api/cases/{case}/snapshots"),
                 ("delete", f"/api/cases/{case}")]
    for role in ("engineer", "coordinator"):
        for method, url in endpoints:
            r = getattr(client, method)(url, headers=hdr[role], **({"json": {"decision": "accept"}} if method == "post" else {}))
            check(f"{method} {url} as {role}", r.status_code in (403, 404))
    for method, url in endpoints[6:]:
        r = getattr(client, method)(url, headers=d["rohan"], **({"json": {"decision": "accept"}} if method == "post" else {}))
        check(f"{method} {url} as departing", r.status_code == 403)

    # 6. Unauthenticated and forged tokens.
    for method, url in endpoints[:6] + [("get", f"/api/cases/{case}/handover"), ("get", "/api/cases")]:
        check(f"anon {url}", getattr(client, method)(url).status_code == 401)
    forged = {"Authorization": "Bearer eyJ1aWQiOiJkZXYiLCJleHAiOjk5OTk5OTk5OTl9.forged"}
    check("forged reviewer token", client.get(f"/api/cases/{case}/ledger", headers=forged).status_code == 401)

    assert probes >= 100, probes
    assert not failures, failures
