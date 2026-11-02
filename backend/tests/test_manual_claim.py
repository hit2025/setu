"""Round 1 fallback: evidence-linked manual claim creation by the reviewer."""


def test_manual_claim_is_anchored_and_access_derived(client, demo):
    d = demo
    srcs = client.get(f"/api/cases/{d['case']}/sources", headers=d["dev"]).json()
    readme = client.get(f"/api/sources/{next(s['id'] for s in srcs if s['filename'] == 'README.md')}", headers=d["dev"]).json()
    span = "PostgreSQL 16"
    start = readme["content"].index(span)
    body = {"source_id": readme["id"], "start": start, "end": start + len(span), "ctype": "decision",
            "subject": "Primary database", "value": "PostgreSQL 16"}
    assert client.post(f"/api/cases/{d['case']}/claims", headers=d["meera"], json=body).status_code == 403
    r = client.post(f"/api/cases/{d['case']}/claims", headers=d["dev"], json=body)
    assert r.status_code == 200
    claim = next(c for c in client.get(f"/api/cases/{d['case']}/ledger", headers=d["dev"]).json()["claims"] if c["id"] == r.json()["id"])
    assert claim["origin"] == "manual" and claim["anchored"] and claim["support"] == "supported"
    assert claim["evidence"][0]["quote"] == span and "coordinator" in claim["allowed_roles"]
    bad = dict(body, start=10_000_000, end=10_000_010)
    assert client.post(f"/api/cases/{d['case']}/claims", headers=d["dev"], json=bad).status_code == 400
