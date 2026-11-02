"""Extractor selection. CSV and repository-activity exports are structured, so the rule
extractor handles them exactly; free text goes to Claude when available."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

from ..config import EXTRACTOR_MODE
from . import rules

log = logging.getLogger("setu.extract")
_llm_ok: bool | None = None


def llm_available() -> bool:
    global _llm_ok
    if EXTRACTOR_MODE == "rules":
        return False
    if _llm_ok is None:
        _llm_ok = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip() or (os.getenv("ANTHROPIC_AUTH_TOKEN") or "").strip())
        if not _llm_ok and shutil.which("ant"):
            try:
                r = subprocess.run(["ant", "auth", "status"], capture_output=True, text=True, timeout=5)
                _llm_ok = r.returncode == 0 and "no active" not in (r.stdout + r.stderr).lower()
            except Exception:  # noqa: BLE001
                _llm_ok = False
    return _llm_ok


def describe() -> dict:
    if llm_available():
        from ..config import LLM_MODEL
        return {"mode": "llm", "label": f"Claude ({LLM_MODEL}) + deterministic parsers", "model": LLM_MODEL}
    return {"mode": "rules", "label": "Deterministic rule extractor (offline)", "model": None}


def extract_source(source, passages, people) -> tuple[list, str, str]:
    """Return (candidates, extractor_name, warning)."""
    structured = source.kind == "csv" or (source.kind == "json" and passages and passages[0].context == "repository activity")
    if structured or not llm_available():
        return rules.extract(source, passages, people), "rules", ""
    try:
        from . import llm
        return llm.extract(source, passages, people), "llm", ""
    except Exception as exc:  # noqa: BLE001 - any model failure falls back, visibly
        log.warning("LLM extraction failed for %s: %s", source.filename, exc)
        if EXTRACTOR_MODE == "llm":
            raise
        cause = exc.__cause__ or exc.__context__
        why = f"{type(exc).__name__}: {type(cause).__name__}" if cause else type(exc).__name__
        return rules.extract(source, passages, people), "rules-fallback", f"Model extraction failed ({why}); used rule extractor."
