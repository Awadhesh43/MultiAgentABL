# Agentic ABL Lifecycle Demo

> **Looking for the full web app?** See [WEBAPP_README.md](WEBAPP_README.md) for the Angular +
> FastAPI build (`backend/` + `frontend/`) — a real UI with a HITL approval queue, guardrail
> tiers, a hash-chained audit trail, and configurable document intake. This README covers the
> original terminal-based CLI demo below.

A working, runnable demonstration of the multi-agent system described in
`ABL_Agentic_AI_HLD.html` and `ABL_Agentic_AI_TechStack.html`: eleven
Claude-powered agents covering the ABL lifecycle from origination through
portfolio monitoring, an ABL Wiki agent grounded in a Chroma-indexed
knowledge base, and a supervisor that enforces a human-approval gate before
any deal record is changed.

This is a local, single-process stand-in for the enterprise stack in the
tech stack doc: ChromaDB stands in for the OpenSearch vector store, the deal
JSON files stand in for the loan servicing system, and the JSONL audit log
stands in for the WORM-backed ledger — same shape, demo-scale infrastructure.

## What's in here

```
data/knowledge_base/       6 Markdown articles: glossary, borrowing base
                            mechanics, lifecycle playbook, covenants, field
                            exams, governance -- the ABL Wiki agent's source
                            of truth, chunked and indexed into ChromaDB.
data/deals/                One seeded demo deal: Meridian Apparel Group,
                            a $15M ABL revolver mid-way through servicing.
data/borrowing_base_certificates/
                            Four weeks of processed BBC history showing a
                            softening trend, plus one raw, unprocessed
                            submission for the Borrowing Base agent to
                            work through live.
src/abl_agents/
  calculations.py           Deterministic borrowing base / FCCR math --
                             agents call this, they never do the arithmetic.
  knowledge_base.py          Markdown -> ChromaDB ingestion and retrieval.
  deal_store.py               Mock system of record: reads are open, writes
                               only happen through apply_change.
  audit_log.py                 Append-only, hash-chained JSONL audit trail.
  tools.py                      The shared tool catalog every agent draws from.
  agent.py                      One generic tool-calling agent wrapper.
  registry.py                    The 11 agent definitions as data.
  orchestrator.py                 Runs one agent against the deal and enforces
                                   the human-in-the-loop gate on every proposed
                                   change.
  cli.py                           Interactive terminal demo.
run_demo.py                 Entry point: `python run_demo.py`.
scripts/smoke_test.py       Non-LLM sanity checks (math + retrieval).
```

## Setup

1. **Python 3.10+** is required (developed against 3.13).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set your Anthropic API key:
   ```
   cp .env.example .env
   # edit .env and paste your ANTHROPIC_API_KEY
   ```
   The audit log viewer and the knowledge-base rebuild work without a key;
   every agent (including the Wiki agent) requires one.

## Run it

```
python run_demo.py
```

You'll land on a menu:

1. **Run full ABL lifecycle demo** — walks the Meridian Apparel deal through
   all nine sequential stages (origination through renewal), one agent per
   stage, pausing at every proposed change for your approval.
2. **Run a single lifecycle stage** — same, for one stage at a time.
3. **Chat with the ABL Wiki agent** — open-ended Q&A grounded in the
   knowledge base, with citations shown after every answer.
4. **Process the pending Borrowing Base Certificate** — the Borrowing Base
   agent works through this week's raw, unprocessed BBC submission
   (a customer bankruptcy write-off plus a same-day draw request), shows
   its math, and — on your approval — commits it to the deal's official
   history and funds the draw if the availability supports it.
5. **View audit log** — every agent recommendation and every human decision,
   with hash-chain integrity verification.
6. **Rebuild knowledge base index** — re-indexes the Markdown KB into Chroma.

First run of options 3, 4, or the knowledge-base search downloads a small
(~80MB) local embedding model (`all-MiniLM-L6-v2`) via ChromaDB's default
embedding function; after that it runs fully offline.

### Try this first

Run option **4** before option **1** — the pending BBC submission is the
most concrete demonstration of the whole design: real (synthetic) numbers
go in, the agent calls `calculate_borrowing_base` rather than doing the
arithmetic itself, cites the dilution-reserve rule it's applying, flags that
the requested draw isn't fully fundable, and nothing is written to the deal
record until you approve it at the prompt.

## Sanity-check without an API key

```
python scripts/smoke_test.py
```

Verifies the borrowing base / FCCR math against hand-checked figures and
confirms ChromaDB ingestion and retrieval are working, with no LLM calls.

## Resetting the demo

Options 1 and 4 write to `data/deals/meridian_apparel.json`,
`data/borrowing_base_certificates/meridian_apparel_bbc_history.json`, and
`logs/audit_log.jsonl`. To reset to the original seeded state, restore those
three files from version control (or re-copy them if you're not using git),
and delete `logs/audit_log.jsonl`.

## Design notes carried over from the HLD

- **Advise, never decide.** Every agent's tool catalog includes read/search/
  calculate tools it can call freely, and exactly one write path —
  `propose_change` — which only *stages* a change. The orchestrator is the
  only code that ever calls `deal_store.apply_change`, and only after a
  human approves.
- **Grounded, cited answers.** The Wiki agent (and every other agent, when
  it states a term or policy rule) is instructed to call
  `search_knowledge_base` and cite what it retrieves rather than answer ABL
  policy questions from general model knowledge.
- **Structural audit trail.** `audit_log.py` hash-chains every entry to the
  one before it — the same "audit is a byproduct of the architecture, not a
  bolted-on log statement" principle from the tech stack doc, implemented
  directly rather than deferred to a managed ledger service.
