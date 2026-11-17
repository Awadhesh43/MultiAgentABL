"""Records and scores every agent call, feeding the agent eval view.

Each call to an agent (the Document Intake Agent, the stage agents, the ABL
Wiki agent, the Borrowing Base agent) is recorded as an AgentCall row: what it
was asked, what it answered, how long it took, how many tokens it used and how
it was answered (LLM, rule-based, retrieval only).

Quality is scored without a second LLM call, so scoring is free, fast and
repeatable, but the scores are proxies and are labelled as such in the UI:

- context_relevance: how close the passages the agent retrieved were to what it
  was looking for (cosine similarity of the embeddings, averaged).
- answer_relevance: cosine similarity between the answer and the question.
- groundedness: for a written answer, the share of its sentences that are
  supported by the context the agent was given (best embedding similarity of the
  sentence to any context sentence >= GROUNDED_SUPPORT_THRESHOLD). For document
  intake it is the share of extracted values that literally appear in the
  passage they were read from.
- accuracy: not scored automatically. It comes from what humans did with the
  output -- fields a reviewer accepted unchanged, proposed changes an approver
  approved, or an explicit thumbs up/down (see compute_accuracies).

Scoring failures never break the agent call being recorded: they are noted in
the call's details instead.
"""
from __future__ import annotations

import math
import re
import threading
from collections import defaultdict
from time import perf_counter

from sqlalchemy.orm import Session

from .models import AgentCall, ExtractedField, PendingChange

# Calibrated on the ABL knowledge base: sentences it supports score 0.61-0.88 against
# it, plausible-sounding claims it does not support score 0.23-0.46.
GROUNDED_SUPPORT_THRESHOLD = 0.55

_MAX_TEXT = 6000


# ---- scoring primitives ---------------------------------------------------------------------

_embedder = None
_embed_lock = threading.Lock()


def _embed(texts: list[str]):
    """Unit-length embeddings from the same ONNX MiniLM model the knowledge base uses."""
    import numpy as np

    global _embedder
    with _embed_lock:
        if _embedder is None:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            _embedder = DefaultEmbeddingFunction()
        vectors = np.array(_embedder(texts), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def similarity_from_distance(distance: float) -> float:
    """Chroma reports squared L2 distance between unit vectors, which is
    2 - 2*cosine, so cosine similarity is 1 - distance/2."""
    return max(0.0, min(1.0, 1.0 - distance / 2.0))


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_LEADING_MARKER_RE = re.compile(r"^[\s\-*•#>\d.)]+")


def split_sentences(text: str, min_words: int = 4) -> list[str]:
    parts = (_LEADING_MARKER_RE.sub("", p).replace("**", "").strip() for p in _SENTENCE_SPLIT_RE.split(text))
    return [p for p in parts if len(p.split()) >= min_words]


def groundedness(answer: str, context: list[str]) -> tuple[float | None, list[dict]]:
    """Share of the answer's sentences supported by the context, plus the
    per-sentence detail. None if there is nothing to compare."""
    sentences = split_sentences(answer)
    units = [u for chunk in context for u in split_sentences(chunk, min_words=3)]
    if not sentences or not units:
        return None, []
    sims = _embed(sentences) @ _embed(units).T
    best = sims.max(axis=1)
    best_at = sims.argmax(axis=1)
    rows = [
        {
            "sentence": s, "support": round(float(b), 3), "supported": bool(b >= GROUNDED_SUPPORT_THRESHOLD),
            "closest_context": units[int(i)][:240],
        }
        for s, b, i in zip(sentences, best, best_at)
    ]
    return round(sum(r["supported"] for r in rows) / len(rows), 3), rows


def answer_relevance(answer: str, query: str) -> float | None:
    if not answer.strip() or not query.strip():
        return None
    vectors = _embed([answer[:2000], query])
    return round(max(0.0, min(1.0, float(vectors[0] @ vectors[1]))), 3)


_NUMBER_TOKEN_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _as_number(text: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def value_supported(value: str, data_type: str, source_text: str) -> bool:
    """True if an extracted value can be found in the passage it was read from.
    Numbers are compared as numbers (the extractor reformats "5500000" to
    "$5,500,000"); everything else as text ignoring case, spacing and punctuation."""
    if not value or not source_text:
        return False
    if data_type in ("currency", "number", "percent"):
        target = _as_number(value)
        if target is not None:
            return any(
                (n := _as_number(tok)) is not None and abs(n - target) < 1e-6
                for tok in _NUMBER_TOKEN_RE.findall(source_text)
            )
    return _squash(value) in _squash(source_text)


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


# ---- recording ----------------------------------------------------------------------------------

class CallRecorder:
    """Times and stores one agent call. Use as a context manager around the
    agent's work only, so latency doesn't include the caller's own DB work:

        with agent_eval.record(db, "wiki", "ABL Wiki Agent", mode="llm", input_summary=q) as rec:
            ...
            rec.set_usage(response.usage)
            rec.eval_input["answer"] = answer

    On success the row is added to the session (the caller's commit persists
    it). If the block raises, the failure is committed on its own -- so a call
    that 500s is still on record -- and the exception propagates unchanged."""

    def __init__(self, db: Session, agent_kind: str, agent_name: str, **fields) -> None:
        self.db = db
        self.row = AgentCall(agent_kind=agent_kind, agent_name=agent_name, **fields)
        self.details: dict = {}
        # What the scorer needs; filled in by the caller inside the with-block.
        # Recognised keys: answer, query, context (list[str]), retrieval_distances,
        # intake (IntakeResult), key_terms (list[dict]).
        self.eval_input: dict = {}
        self._started = 0.0

    def __enter__(self) -> "CallRecorder":
        self._started = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.row.latency_ms = round((perf_counter() - self._started) * 1000, 1)
        if exc_type is not None:
            self.row.status = "error"
            self.row.error = f"{exc_type.__name__}: {exc}"[:2000]
            self.row.details = dict(self.details)
            try:
                self.db.rollback()
                self.db.add(self.row)
                self.db.commit()
            except Exception:  # noqa: BLE001 - never mask the original error
                self.db.rollback()
            return False

        try:
            self._score()
        except Exception as scoring_error:  # noqa: BLE001 - scoring must not fail the call
            self.details["eval_error"] = f"{type(scoring_error).__name__}: {scoring_error}"
        self.row.details = dict(self.details)
        self.db.add(self.row)
        self.db.flush()
        return False

    # -- helpers for callers ---------------------------------------------------------------

    def set_usage(self, usage) -> None:
        """Token counts from an Anthropic response's `usage`."""
        if usage is None:
            return
        self.row.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        self.row.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        self.row.cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.row.cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    def set_output(self, text: str) -> None:
        self.row.output_summary = (text or "")[:_MAX_TEXT]

    def absorb_stage_result(self, rec: dict) -> None:
        """Takes what recommendations.run_stage returned -- the answer plus its
        "_eval" entry -- and records how it was produced."""
        ev = rec.get("_eval") or {}
        self.row.mode = rec.get("source", self.row.mode)
        self.set_output(rec.get("text", ""))
        self.row.retrieval_ms = ev.get("retrieval_ms")
        self.row.llm_ms = ev.get("llm_ms")
        self.set_usage(ev.get("usage"))
        if ev.get("model"):
            self.row.model = ev["model"]
        if ev.get("llm_error"):
            # The LLM path failed and the rule-based answer was returned instead.
            self.row.status, self.row.error, self.row.model = "fallback", ev["llm_error"], ""
        self.update_details(stop_reason=ev.get("stop_reason"), retrieval=ev.get("retrieval", []))
        self.eval_input = {
            "answer": rec.get("text", ""), "query": ev.get("query", ""), "context": ev.get("context", []),
            "retrieval_distances": ev.get("retrieval_distances", []),
        }

    def update_details(self, **items) -> None:
        """Adds to the call's details. Also safe to call after the with-block."""
        self.details.update(items)
        self.row.details = dict(self.details)  # reassign so SQLAlchemy sees the JSON change

    # -- scoring ---------------------------------------------------------------------------------

    def _score(self) -> None:
        ei = self.eval_input
        if ei.get("intake") is not None:
            self._score_intake(ei["intake"], ei.get("key_terms", []))

        distances = ei.get("retrieval_distances")
        if distances:
            self.row.context_relevance = _mean([similarity_from_distance(d) for d in distances])

        answer = ei.get("answer", "")
        # Only a model-written answer can be ungrounded or off-topic: rule-based
        # and retrieval-only answers are assembled from the context or from
        # computed figures, so scoring them would just report 1.0 or noise.
        if answer and self.row.mode == "llm":
            if ei.get("context"):
                score, rows = groundedness(answer, ei["context"])
                self.row.groundedness = score
                if rows:
                    self.details["sentence_support"] = rows
            if ei.get("query"):
                self.row.answer_relevance = answer_relevance(answer, ei["query"])

    def _score_intake(self, result, key_terms: list[dict]) -> None:
        types = {t["id"]: t.get("data_type", "text") for t in key_terms}
        checked = supported = 0
        similarities: list[float] = []
        for candidate in result.candidates:
            used = next((e for e in candidate.evidence if e.used), None)
            if used is None:
                continue
            if used.distance is not None:
                similarities.append(similarity_from_distance(used.distance))
            if candidate.value:
                checked += 1
                chunk = result.chunks[used.chunk_index]
                if value_supported(candidate.value, types.get(candidate.key_term_id, "text"), chunk.text):
                    supported += 1
        found = sum(1 for c in result.candidates if c.value)
        self.row.groundedness = round(supported / checked, 3) if checked else None
        self.row.context_relevance = _mean(similarities)
        self.details.update(
            key_terms=len(result.candidates), fields_found=found,
            coverage=round(found / len(result.candidates), 3) if result.candidates else None,
            mean_confidence=_mean([c.confidence for c in result.candidates if c.value]),
            page_count=result.page_count, page_source=result.page_source, **result.metrics,
        )
        self.row.retrieval_ms = result.metrics.get("retrieval_ms")


def record(db: Session, agent_kind: str, agent_name: str, **fields) -> CallRecorder:
    return CallRecorder(db, agent_kind, agent_name, **fields)


# ---- accuracy (derived from what humans did) -------------------------------------------------------

def _same_value(a: str, b: str) -> bool:
    return " ".join(a.split()).lower() == " ".join(b.split()).lower()


def compute_accuracies(db: Session, calls: list[AgentCall]) -> dict[str, tuple[float | None, str]]:
    """{call id: (accuracy 0..1 or None, plain-language basis)}. Batched: one query
    for all intake documents' fields and one for all proposed changes."""
    document_ids = {c.document_id for c in calls if c.agent_kind == "document_intake" and c.document_id}
    fields_by_doc: dict[str, list[ExtractedField]] = defaultdict(list)
    if document_ids:
        for f in db.query(ExtractedField).filter(ExtractedField.document_id.in_(document_ids)):
            fields_by_doc[f.document_id].append(f)

    change_ids = {i for c in calls for i in (c.details or {}).get("pending_change_ids", [])}
    change_status: dict[str, str] = {}
    if change_ids:
        for pc in db.query(PendingChange.id, PendingChange.status).filter(PendingChange.id.in_(change_ids)):
            change_status[pc.id] = pc.status

    out: dict[str, tuple[float | None, str]] = {}
    for call in calls:
        value, basis = None, ""
        if call.agent_kind == "document_intake" and call.document_id:
            fields = fields_by_doc.get(call.document_id, [])
            # Fields where the agent found nothing aren't scored: a reviewer
            # rejecting an empty field is agreement, not a miss.
            scored = [f for f in fields if f.original_value and f.status != "pending_review"]
            correct = sum(1 for f in scored if f.status == "confirmed" and _same_value(f.extracted_value, f.original_value))
            waiting = sum(1 for f in fields if f.status == "pending_review")
            if scored:
                value = round(correct / len(scored), 3)
                basis = f"{correct} of {len(scored)} reviewed values accepted exactly as extracted"
            else:
                basis = "no extracted values reviewed yet"
            if waiting:
                basis += f" ({waiting} awaiting review)"
        elif (call.details or {}).get("pending_change_ids") is not None and call.agent_kind in ("stage_agent", "borrowing_base"):
            ids = call.details.get("pending_change_ids", [])
            statuses = [change_status.get(i) for i in ids if i in change_status]
            approved, rejected = statuses.count("approved"), statuses.count("rejected")
            decided = approved + rejected
            if not ids:
                basis = "proposed no changes, so there is nothing to approve or reject"
            elif decided:
                value = round(approved / decided, 3)
                basis = f"{approved} of {decided} proposed changes approved"
                if len(ids) > decided:
                    basis += f" ({len(ids) - decided} pending)"
            else:
                basis = f"{len(ids)} proposed change(s) awaiting a decision"
        elif call.human_rating:
            value = 1.0 if call.human_rating == "up" else 0.0
            basis = "human thumbs " + call.human_rating
        else:
            basis = "no human feedback recorded yet"
        out[call.id] = (value, basis)
    return out


# ---- aggregation for the summary view ----------------------------------------------------------------

def _percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo), 1)


def aggregate(calls: list[AgentCall], accuracies: dict[str, tuple[float | None, str]]) -> dict:
    latencies = sorted(c.latency_ms for c in calls)
    llm_calls = [c for c in calls if c.input_tokens is not None]
    acc_values = [accuracies[c.id][0] for c in calls if accuracies.get(c.id, (None,))[0] is not None]
    return {
        "calls": len(calls),
        "success": sum(1 for c in calls if c.status == "success"),
        "fallback": sum(1 for c in calls if c.status == "fallback"),
        "error": sum(1 for c in calls if c.status == "error"),
        "llm_calls": sum(1 for c in calls if c.mode == "llm"),
        "latency_avg_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "latency_p50_ms": _percentile(latencies, 0.5),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "input_tokens": sum(c.input_tokens or 0 for c in llm_calls),
        "output_tokens": sum(c.output_tokens or 0 for c in llm_calls),
        "avg_tokens_per_llm_call": round(sum((c.input_tokens or 0) + (c.output_tokens or 0) for c in llm_calls) / len(llm_calls)) if llm_calls else None,
        "groundedness": _mean([c.groundedness for c in calls]),
        "context_relevance": _mean([c.context_relevance for c in calls]),
        "answer_relevance": _mean([c.answer_relevance for c in calls]),
        "accuracy": _mean(acc_values),
        "accuracy_evaluated": len(acc_values),
        "thumbs_up": sum(1 for c in calls if c.human_rating == "up"),
        "thumbs_down": sum(1 for c in calls if c.human_rating == "down"),
    }
