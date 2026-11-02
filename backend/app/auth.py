"""Demo-grade authentication: signed bearer tokens for four seeded personas.
Every API call resolves the caller's role from the token on the server."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import SECRET_KEY
from .db import get_db
from .models import User

PERSONAS = [
    {"id": "dev", "name": "Dev Malhotra", "role": "reviewer", "title": "Faculty project reviewer"},
    {"id": "rohan", "name": "Rohan Das", "role": "departing", "title": "Outgoing backend lead"},
    {"id": "meera", "name": "Meera Iyer", "role": "engineer", "title": "Incoming engineer"},
    {"id": "ananya", "name": "Ananya Sen", "role": "coordinator", "title": "Incoming event coordinator"},
]
TOKEN_TTL = 7 * 24 * 3600


def seed_users(db: Session) -> None:
    for p in PERSONAS:
        if db.get(User, p["id"]) is None:
            db.add(User(**p))
    db.commit()


def _sign(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(SECRET_KEY.encode(), payload, hashlib.sha256).digest()).decode().rstrip("=")


def issue_token(user: User) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"uid": user.id, "exp": int(time.time()) + TOKEN_TTL}).encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload.encode())}"


def _decode(token: str) -> str | None:
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload.encode())):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data.get("exp", 0) < time.time():
            return None
        return data["uid"]
    except Exception:  # noqa: BLE001
        return None


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    uid = _decode(authorization.split(" ", 1)[1].strip())
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(401, "Invalid or expired session")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This action requires role: {', '.join(roles)}")
        return user
    return dep
