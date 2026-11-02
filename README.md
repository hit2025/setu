# SETU · by Team KavachX

**Turns scattered project activity into an approved, evidence-backed, role-filtered handover when a team member leaves.**

> AI proposes. Deterministic code checks. Humans approve.

**Live app:** https://setu-kavachx.onrender.com (free hosting: the first visit after 15 idle minutes takes about a minute to wake up, and data resets to empty)

SETU does not summarise documents into polished prose. It reconstructs the project as a ledger of typed, cited claims
(decisions, owners, tasks, deadlines, dependencies, risks, contacts), **rehearses every next action** to see whether it
can actually proceed, turns what is missing into targeted questions for the person who is leaving, and releases a
reviewer-approved version that each successor sees through a server-side permission filter.

---

## 5-minute judge journey

Open the app → pick a persona (no password) → follow the **Next step** card on each case.

| # | Persona | What to do | What it proves |
|---|---------|------------|----------------|
| 1 | Dev (reviewer) | **Load CampusConnect demo** | 7 authorised files imported with access labels, SHA-256 hashes; a leaked DB URL, email and phone are masked |
| 2 | Dev | **02 Reconstruct → Run** | ~60 typed claims, each tied to an exact character span. The confidential HR note is never extracted |
| 3 | Dev | **03 Verify** | README says hosting = *Railway*, #backend chat says *Render*. Both kept side by side; nothing auto-resolved |
| 4 | Dev | Readiness rehearsal | *Deploy release v1.2* is **Blocked**: hosting unresolved, migration 014 in progress, PR #45 in review. Rohan's tasks flagged *Owner leaving* |
| 5 | Rohan (departing) | Answer gap questions | Answers become **labelled testimony** with their own hash, never facts |
| 6 | Dev | Resolve conflicts, verify testimony, bulk-accept, **05 Release → Approve** | Approval gate re-verifies every anchor; immutable hashed v1 |
| 7 | Meera (engineer) | Open handover | First correct action, ranked actions, tacit workaround + Rohan's verified steps, every item cited. **Acknowledge** |
| 8 | Ananya (coordinator) | Open handover | Only deadlines, owners and schedule work. Engineering, finance and HR content absent — also from search and citation links |

## Features (Round 2)

- **Connect** – drag-and-drop upload of `.md / .txt / .csv / .json` (chat exports and repository activity are normalised to timestamped lines); per-file access label; raw + canonical SHA-256; secret/PII masking *before* storage; 50-file / 100k-character case limits; de-duplication by hash; relabelling re-derives access for every dependent claim.
- **Reconstruct** – background job (Postgres-style job table + worker thread, live progress) that extracts typed claims with **Claude (`claude-opus-5-5`, JSON-schema structured output)** when a key is configured, or a **deterministic offline rule extractor** otherwise. Structured CSV/activity exports always use exact parsers. Cross-source task linking (e.g. meeting-note action items ↔ `T-106`). Re-runs preserve review decisions.
- **Verify** – four gates in code: exact-span anchoring + hash check, conflict reconciliation (attribute/value), lexical support check (weak/unsupported labelled), access derivation (intersection of every supporting source's readers). Proposals are kept separate from decisions; tacit workarounds are flagged.
- **Readiness rehearsal** – every action is checked for a staying owner, agreed date, exact evidence and satisfied direct prerequisites (tasks, decisions, PRs). Ranked: ready → owner leaving → needs owner → blocked → done. Dependency graph view.
- **Gap-closure loop** – conflicts, missing owners, departing-owner tasks/areas, unknown prerequisites and tacit workarounds become targeted questions for the departing member. Answers are stored as testimony sources with exact anchors and must be verified by the reviewer; accepted answers update readiness.
- **Review** – accept / edit (re-checked against evidence) / reject / undo per claim, side-by-side conflict resolution (agreeing claims corroborate; others are superseded), explicit "keep unresolved", bulk-accept of fully supported claims, manual evidence-linked claim creation by selecting text in a source (fallback path).
- **Approve & release** – approval gate (no pending claims, no open conflicts, all anchors valid, something changed), immutable content-hashed versions with diff counts, permission preview per role.
- **Handover** – server-filtered recipient views: first correct action (viewer's own work first), ranked actions with checks and blockers, unresolved items, verified decisions, proposals, risks & tacit knowledge, ownership map, contacts, timeline, search, open questions, visible sources only. Citations re-check access and source integrity on every open. Version-bound receipt acknowledgement with view hash.
- **Quality gates panel** – citation integrity, unsupported-as-verified, testimony verification, measured live against the Round 1 targets.
- **Audit log** – uploads, extraction, every review decision, answers, approvals, handover opens, citation opens, receipts.

## Architecture

```
React + TypeScript (Vite)  ──►  FastAPI + Pydantic  ──►  SQLAlchemy (SQLite default / PostgreSQL)
                                   │
                                   ├─ ingest.py      canonicalise · mask · hash · passages
                                   ├─ extract/       Claude structured output  |  offline rule extractor
                                   ├─ verify.py      anchor · reconcile · support · access
                                   ├─ readiness.py   action rehearsal · gap questions · timeline
                                   ├─ snapshot.py    approval gate · immutable versions · role filter
                                   ├─ worker.py      job table + worker thread
                                   └─ policy.py      deny-by-default label → role matrix
```

| Label | Reviewer | Departing | Engineer | Coordinator |
|---|:-:|:-:|:-:|:-:|
| public / team | ✓ | ✓ | ✓ | ✓ |
| engineering | ✓ | ✓ | ✓ | – |
| finance | ✓ | – | – | – |
| confidential (never extracted) | ✓ | – | – | – |

## Install and run (Windows cmd)

```
cd /d D:\kavachx\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd /d D:\kavachx\frontend
npm install
npm run build
cd /d D:\kavachx\backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**.

**Reset demo data:** delete a case with the bin icon on the case list (as Dev), or stop the server and delete `backend\data` for a completely empty start.
**Port busy:** use `--port 8001` and open http://localhost:8001.
**UI live-reload while editing:** run `npm run dev` in `frontend` and open http://localhost:5173 (API calls go to port 8000).

**AI extraction:** put `ANTHROPIC_API_KEY=...` in `backend\.env` (see `.env.example`). Without a key everything still works with the offline extractor, and the badge in the app shows which engine is active.

## Deploy

- **Docker:** `docker build -t setu . && docker run -p 8000:8000 setu`
- **Render:** push to GitHub → New → Blueprint → select the repo (`render.yaml` included). Add `ANTHROPIC_API_KEY` if you want Claude extraction.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q
```

15 tests including the full judge journey, exact-anchor validity for every claim, testimony-not-fact, the approval gate, a mocked-model contract test (paraphrased quotes are rejected), manual evidence-linked claims, and **100+ adversarial access probes** (cross-role citation replay, search leakage, role impersonation, recipient write attempts, forged/absent tokens) with zero disclosures.

## Team KavachX

Supratim Roy (Team Leader – product architecture & AI pipeline) · Elora Pradhan (security, data & QA) · Swastik Mitra (backend & deployment) · Sunanda Samanta (frontend & UX)
