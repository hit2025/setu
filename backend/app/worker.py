"""Postgres-style job table + in-process worker thread (no separate queue service).
On PostgreSQL the claim query uses FOR UPDATE SKIP LOCKED so several workers can run."""
from __future__ import annotations

import logging
import threading
import time
import traceback

from .db import SessionLocal, engine
from .models import Case, Job, now
from .pipeline import run_reconstruction

log = logging.getLogger("setu.worker")
_stop = threading.Event()
_thread: threading.Thread | None = None


def _claim_job() -> str | None:
    db = SessionLocal()
    try:
        q = db.query(Job).filter(Job.status == "queued").order_by(Job.created_at)
        if engine.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        job = q.first()
        if job is None:
            return None
        job.status, job.started_at, job.progress, job.message = "running", now(), 5, "Starting reconstruction"
        db.commit()
        return job.id
    finally:
        db.close()


_live: dict[str, tuple[int, str]] = {}


def _set_progress(job_id: str, pct: int, msg: str) -> None:
    # Kept in memory: the pipeline holds the DB write transaction while it runs.
    _live[job_id] = (pct, msg)


def live_progress(job_id: str) -> tuple[int, str] | None:
    return _live.get(job_id)


def run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        result = run_reconstruction(db, job.case_id, lambda p, m: _set_progress(job_id, p, m))
        job = db.get(Job, job_id)
        job.status, job.progress, job.message, job.result, job.finished_at = "done", 100, "Reconstruction complete", result, now()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.error("Job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
        job = db.get(Job, job_id)
        if job:
            job.status, job.message, job.finished_at = "failed", str(exc), now()
            case = db.get(Case, job.case_id)
            if case and case.status == "reconstructing":
                case.status = "collecting"
            db.commit()
    finally:
        _live.pop(job_id, None)
        db.close()


def _loop() -> None:
    while not _stop.is_set():
        try:
            job_id = _claim_job()
            if job_id:
                run_job(job_id)
                continue
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
        _stop.wait(0.4)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    # Recover jobs interrupted by a restart.
    db = SessionLocal()
    try:
        for job in db.query(Job).filter(Job.status == "running").all():
            job.status, job.message = "queued", "Re-queued after restart"
        db.commit()
    finally:
        db.close()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="setu-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
