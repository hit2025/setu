from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditEvent


def log(db: Session, case_id: str | None, actor: str, action: str, detail: dict | None = None) -> None:
    db.add(AuditEvent(case_id=case_id, actor=actor, action=action, detail=detail or {}))
