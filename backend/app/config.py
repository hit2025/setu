"""Runtime configuration. Everything is overridable through environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("SETU_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite by default for a zero-setup judge run; set DATABASE_URL=postgresql+psycopg://... for Postgres.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'setu.db').as_posix()}")

SECRET_KEY = os.getenv("SETU_SECRET_KEY", "setu-dev-secret-change-in-production")

# auto = use Claude when credentials exist, otherwise the deterministic rule extractor.
EXTRACTOR_MODE = os.getenv("SETU_EXTRACTOR", "auto").lower()  # auto | llm | rules
LLM_MODEL = os.getenv("SETU_LLM_MODEL", "claude-opus-5-5")
LLM_TIMEOUT_S = float(os.getenv("SETU_LLM_TIMEOUT", "90"))

# Scope limits from the Round 1 plan (one case: <=50 files, <=100k extracted characters).
MAX_FILES_PER_CASE = 50
MAX_CHARS_PER_CASE = 100_000
MAX_FILE_BYTES = 2_000_000

DEMO_DIR = BASE_DIR / "demo_data" / "campusconnect"
FRONTEND_DIST = Path(os.getenv("SETU_FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
