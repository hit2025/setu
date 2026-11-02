"""The model is untrusted: its claims are kept only if the quote is verbatim in the passage."""
from types import SimpleNamespace as NS

from app.extract import llm
from app.ingest import canonicalize


def test_llm_output_is_anchored_or_rejected(monkeypatch):
    raw = b"# Notes\n- Decision: Hosting platform is Render.\n- Meera owns the QR service.\n"
    doc = canonicalize("notes.md", raw)
    src = NS(filename="notes.md", kind=doc.kind, content=doc.content)
    passages = [NS(id=f"s:p{p.idx}", text=p.text, start=p.start, end=p.end, context=p.context, occurred_at="") for p in doc.passages]
    fake = {"claims": [
        {"passage": 0, "ctype": "decision", "subject": "Hosting platform", "attribute": "hosting platform", "value": "Render",
         "statement": "Hosting is Render", "modality": "decision", "quote": "Decision: Hosting platform is Render."},
        {"passage": 1, "ctype": "owner", "subject": "QR service", "attribute": "owner: qr service", "value": "Meera Iyer",
         "statement": "Meera owns QR", "modality": "fact", "quote": "Meera is the owner of the QR service"},  # paraphrased
    ]}
    monkeypatch.setattr(llm, "_call", lambda prompt: fake)
    out = llm.extract(src, passages, {"meera": "Meera Iyer"})
    good, bad = out
    assert good.extra["anchored"] and doc.content[good.start:good.end] == "Decision: Hosting platform is Render."
    assert good.attribute == "hosting platform" and good.origin == "llm"
    assert bad.extra["anchored"] is False  # pipeline drops it and counts a rejected citation
