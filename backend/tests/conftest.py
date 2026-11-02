import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="setu-test-")
os.environ["SETU_DATA_DIR"] = _tmp
os.environ["SETU_EXTRACTOR"] = "rules"  # deterministic tests; no network
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, uid):
    r = client.post("/api/auth/login", json={"user_id": uid})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def wait_job(client, h, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}", headers=h).json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("job timed out")


@pytest.fixture(scope="session")
def demo(client):
    """Full judge journey up to an approved v1. Returns ids and headers."""
    dev, rohan = login(client, "dev"), login(client, "rohan")
    case = client.post("/api/cases/demo", headers=dev).json()
    job = client.post(f"/api/cases/{case['id']}/reconstruct", headers=dev).json()
    res = wait_job(client, dev, job["id"])
    assert res["status"] == "done", res
    return {"case": case["id"], "dev": dev, "rohan": rohan, "meera": login(client, "meera"),
            "ananya": login(client, "ananya"), "job": res}
