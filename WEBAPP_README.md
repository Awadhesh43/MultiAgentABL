# Agentic ABL Platform — Web Application

A full-stack demonstration of the ABL lifecycle system from the HLD: an **Angular** frontend
over a **FastAPI + SQLite** backend, covering origination through workout, with a human-in-the-loop
(HITL) approval queue, guardrail enforcement, a hash-chained audit trail, and configurable
document intake.

This is a separate, standalone build from the Python CLI demo in `src/abl_agents/` — it has its
own database, its own agent-recommendation logic, and a real web UI. Both share the same
knowledge base (`data/knowledge_base/`, indexed into the same ChromaDB store) and the same
borrowing-base math (`src/abl_agents/calculations.py`).

```
backend/    FastAPI + SQLAlchemy (SQLite) API, document parser, seed script
frontend/   Angular 22 + Angular Material app
```

## Setup

**Backend**
```
cd backend
pip install -r requirements.txt
python seed.py              # creates/resets backend/abl_platform.db with 7 demo deals
python -m uvicorn app.main:app --reload --port 8000
```
Uses the same `ANTHROPIC_API_KEY` as the CLI demo — set it in the project root `.env` (see
`.env.example`). Without a key, every read/write/HITL/audit/document feature still works; the
stage-agent recommendations and the Wiki chat fall back to deterministic, rule-based behavior
instead of an LLM call (see "Works with or without an API key" below).

**Frontend**
```
cd frontend
npm install
npm start                   # ng serve on :4200, proxies /api to :8000 (see proxy.conf.json)
```
Open http://localhost:4200.

**Smoke test** (optional, drives the whole UI headlessly and screenshots every page):
```
cd frontend
npx playwright install chromium   # one-time
npm run verify:ui
```

## The seeded portfolio

`python seed.py` drops and recreates the database with 7 fictional deals, deliberately placed at
different lifecycle stages and different states of deterioration, so every stage and every
guardrail tier is visible immediately without triggering a single agent run:

| Deal | Stage | What it demonstrates |
|---|---|---|
| Harbor Steel Fabricators | Origination | A fresh prospect; a **warn**-tier sizing change pending |
| Vantage Foods Distribution | Underwriting | A **requires elevated approval** risk-rating downgrade pending |
| Crestline Furniture Co. | Documentation & Closing | A **decided history** item — approved advance-rate adjustment |
| Meridian Apparel Group | Covenant Compliance | Carried over from the CLI demo; declining BBC trend, a pending covenant test and watchlist migration |
| Solstice Auto Parts | Covenant Compliance | An active covenant **breach**, plus a **blocked** overadvance draw request |
| Ridgeline Outdoor Supply | Special Assets / Workout | Live overadvance (negative availability), a **rejected** historical decision |
| Palisade Consumer Brands | Renewal & Amendment | A healthy credit; a **warn**-tier upsize request at renewal |

## Feature tour

- **Portfolio dashboard** (`/dashboard`) — every deal, its stage, rating, availability, and open
  HITL count, at a glance.
- **Deal detail** (`/deals/:id`) — a lifecycle timeline (completed / in-progress / not-started per
  stage, plus the workout branch when taken), facility terms, financials, a **"Run a stage
  agent"** panel that produces a grounded recommendation and stages any proposed change, and
  deal-scoped tabs for borrowing base history, approvals, documents, and audit trail.
- **Approvals inbox** (`/approvals`) — every proposed change across the portfolio in one queue,
  filterable by status and by guardrail tier.
- **Document intake** (`/documents`) — each document type (Borrowing Base Certificate, AR Aging
  Report, Financial Statements, Credit Agreement, Field Exam Report, Compliance Certificate) has
  its own list of key terms the parser looks for. Add a term from the UI — label, aliases, data
  type — and the next upload of that type looks for it immediately, no redeploy. Upload a `.txt`,
  `.pdf`, or `.docx` file; the parser extracts a value and a confidence score per key term; a
  human reviews, edits, and confirms each field; confirmed fields can then be mapped onto a deal
  attribute and staged as a normal HITL change.
- **Audit trail** (`/audit`) — every agent recommendation, human decision, document upload, and
  key-term addition, hash-chained end to end with a live integrity check.
- **ABL Wiki** (`/wiki`) — the same retrieval-grounded chat agent as the CLI demo, now with a
  proper chat UI; cites its sources, never proposes or writes anything.

## How HITL and guardrails actually work

Nothing an agent (or a human, via the "Document Intake" apply-to-deal action) proposes is written
to a deal directly. Every proposal becomes a row in the `pending_changes` table with a computed
**guardrail tier**:

- **Pass** — any signed-in role can approve.
- **Warn** — approvable by any role, but flagged (e.g. a facility-term change moves by more than
  10%) so the reviewer sees why before clicking through.
- **Requires elevated approval** — the deciding role must meet or exceed a required authority
  level (e.g. a risk-rating downgrade needs Credit Officer or above; a multi-notch downgrade or a
  covenant breach needs Senior Credit Officer). Enforced server-side — the UI shows who's needed,
  but the API rejects (`403`) a decision from an under-authorized role regardless of what the
  client sends.
- **Blocked** — cannot be approved at all (e.g. a draw that would create an overadvance) without
  an explicit override: the reviewer must check an override box, hold the required authority, and
  write a justification, which is what actually gets recorded in the audit trail — not a silent
  approval.

The "acting as" control in the top-right corner (name + role) is what the approval dialog sends
as the decision's role — switch it to see how the same pending change behaves differently for a
Relationship Manager versus a Senior Credit Officer.

## Works with or without an API key

Every backend feature — deals, HITL, guardrails, audit, document upload and parsing — runs with
plain deterministic code and needs no LLM call at all. Two things specifically call Claude when
`ANTHROPIC_API_KEY` is set, and fall back cleanly when it isn't:

- **"Run a stage agent"** on a deal calls Claude with the deal's data and relevant knowledge-base
  excerpts, using a forced tool call to get back a structured recommendation. Without a key, a
  rule-based fallback still computes real FCCR/covenant/watchlist-trend logic for the stages that
  have a deterministic answer, and returns an honest "no LLM configured" note for the purely
  narrative stages.
- **ABL Wiki chat** calls Claude to turn retrieved knowledge-base passages into a natural-language,
  cited answer. Without a key, it shows the raw retrieved passages directly instead.

The response always includes which path was used (`source: "llm" | "rule_based"` on a stage run;
a wiki answer's citations are shown either way).
