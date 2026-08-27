"""Semantic-search-backed key term extraction tool.

extraction.extract_fields searches the *whole* document for a term's label,
which can be fooled by an earlier, unrelated mention of the same words --
e.g. a document titled "Borrowing Base Certificate" satisfies a plain
search for "Borrowing Base" before the actual "Borrowing Base: $12,876,063"
line ever gets a chance to.

This tool fixes that by chunking the document into semantically coherent
pieces, embedding and storing them in ChromaDB tagged with the document's
own id, then -- for each key term -- running a similarity search scoped to
*only that document's* chunks (via a Chroma `where={"document_id": ...}`
filter, so one document's chunks are never matched against another's) to
find the passage that actually discusses the term. Precise value extraction
(extraction.match_value_in_text) then runs against just that passage.

This is the tool the Document Intake Agent (document_intake_agent.py) calls
once a file has been uploaded and its raw text extracted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import config, extraction
from .extraction import ExtractionCandidate

COLLECTION_NAME = "document_intake_chunks"
_MAX_CHUNK_CHARS = 500
_LOW_RELEVANCE_DISTANCE = 1.4

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Described in the same Anthropic tool-use schema format as the rest of the
# agent catalog (src/abl_agents/tools.py, backend/app/recommendations.py).
# There's no judgment call in *whether* to run this tool once a document is
# uploaded -- see document_intake_agent.py -- so it's invoked directly
# rather than through a model tool_use turn, but it's specified here the
# same way so it could be wired into an LLM's tool list unchanged.
SEMANTIC_EXTRACTION_TOOL = {
    "name": "extract_key_terms_semantic",
    "description": (
        "Chunk and semantically index an uploaded document, then for each key term "
        "configured for its document type, run a similarity search scoped to only "
        "this document's own chunks to locate the passage that discusses the term, "
        "and extract its value from that passage. Returns one result per key term "
        "with a confidence score and which method (semantic or regex fallback) found it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string", "description": "The document's id -- scopes the chunk search so other documents' chunks are never matched."},
            "filename": {"type": "string"},
            "text": {"type": "string", "description": "The document's full extracted text."},
            "key_terms": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "data_type": {"type": "string"},
                    },
                    "required": ["id", "label"],
                },
            },
        },
        "required": ["document_id", "filename", "text", "key_terms"],
    },
}


def _get_collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION_NAME)


@dataclass
class _Chunk:
    text: str
    granularity: str


def semantic_chunks(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[_Chunk]:
    """Structure-aware chunking, not a blind fixed-length window:

    - The document is first split on blank lines into paragraphs -- the
      natural section boundaries of a certificate, statement, or report.
    - A paragraph longer than `max_chars` is re-split on sentence
      boundaries, regrouping sentences up to the size limit.
    - Every individual line inside a *multi-line* paragraph is *also*
      indexed as its own chunk. Financial documents in this domain are
      largely "Label: Value" per line, so a short, dense line like
      "Borrowing Base: $12,876,063" needs to be independently retrievable
      -- not diluted inside a five-line block -- to reliably outrank an
      unrelated mention of the same label elsewhere in the document.

    Returns deduplicated chunks in document order.
    """
    chunks: list[_Chunk] = []
    seen: set[str] = set()

    def add(t: str, granularity: str) -> None:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            chunks.append(_Chunk(t, granularity))

    for para in (p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text.strip())):
        if not para:
            continue
        lines = [l.strip() for l in para.split("\n") if l.strip()]

        if len(para) <= max_chars:
            add(para, "paragraph")
        else:
            buffer = ""
            for sentence in _SENTENCE_SPLIT_RE.split(para):
                candidate = f"{buffer} {sentence}".strip() if buffer else sentence
                if len(candidate) > max_chars and buffer:
                    add(buffer, "paragraph")
                    buffer = sentence
                else:
                    buffer = candidate
            add(buffer, "paragraph")

        if len(lines) > 1:
            for line in lines:
                add(line, "line")

    return chunks


def chunk_and_index_document(document_id: str, filename: str, text: str) -> int:
    """Chunks the document and stores each chunk + its embedding in the
    document-intake ChromaDB collection, tagged with this document's id.
    Returns the number of chunks stored (0 if the document had no usable text)."""
    chunks = semantic_chunks(text)
    if not chunks:
        return 0

    collection = _get_collection()
    ids = [f"{document_id}::{i}" for i in range(len(chunks))]
    documents = [c.text for c in chunks]
    metadatas = [
        {"document_id": document_id, "filename": filename, "chunk_index": i, "granularity": c.granularity}
        for i, c in enumerate(chunks)
    ]
    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


# Natural-language context appended to a phrase before it's embedded, so the
# query itself carries what *kind* of value we're after -- "Borrowing Base"
# alone is equally close to a sentence discussing the concept and a line
# stating its dollar figure, but "Borrowing Base -- a dollar amount" biases
# the embedding toward chunks that actually look like a monetary figure.
# "text" has no format of its own, so it's left unhinted.
_TYPE_QUERY_HINTS = {
    "currency": "a dollar amount",
    "number": "a numeric value",
    "percent": "a percentage",
    "date": "a date",
}


def _query_text_for_phrase(phrase: str, data_type: str) -> str:
    hint = _TYPE_QUERY_HINTS.get(data_type)
    return f"{phrase} -- {hint}" if hint else phrase


def _best_chunks_for_term(collection, document_id: str, label: str, aliases: list[str], data_type: str, top_n: int = 5) -> list[tuple[str, float]]:
    """Queries once per phrase (label, then each alias), every query scoped
    with `where={"document_id": document_id}` so only this document's own
    chunks are ever considered -- another document's chunks living in the
    same collection are invisible to this search. Each query is phrased
    with the term's data_type as context (see _query_text_for_phrase) so
    retrieval itself, not just the regex pass afterward, favors a chunk
    that actually looks like the right kind of value. Returns up to `top_n`
    (chunk_text, distance) pairs merged across all phrase queries, closest
    first."""
    phrases = [label, *aliases] or [label]
    merged: dict[str, float] = {}
    for phrase in phrases:
        result = collection.query(
            query_texts=[_query_text_for_phrase(phrase, data_type)],
            n_results=top_n,
            where={"document_id": document_id},
        )
        docs = (result.get("documents") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for doc_text, distance in zip(docs, dists):
            if doc_text not in merged or distance < merged[doc_text]:
                merged[doc_text] = distance
    ranked = sorted(merged.items(), key=lambda kv: kv[1])
    return ranked[:top_n]


# data_types with an actual value pattern to check the extraction against.
# "text" has no format of its own -- any non-empty grab is acceptable -- so
# it's excluded and never forces the extra chunks to be searched.
_STRICT_TYPES = {"number", "currency", "percent", "date"}
_UNTYPED_MATCH_CONFIDENCE_CAP = 0.4


def extract_key_terms_semantic(document_id: str, filename: str, text: str, key_terms: list[dict]) -> list[ExtractionCandidate]:
    """The tool. For each key term: chunk-scope semantic retrieval first,
    precise regex extraction second, whole-document regex as a last resort.

    The key term's data_type shapes both ends of that retrieval: the
    similarity query itself is phrased with the expected kind of value
    (_query_text_for_phrase) so a currency field's search leans toward
    chunks that look like dollar amounts in the first place, and a typed
    field (currency, number, percent, date) still won't accept a chunk
    whose matched text doesn't actually look like that type just because
    it's the closest one -- the search keeps going through the next-best
    chunks for one that both mentions the term *and* contains a properly
    formatted value, only falling back to the best untyped text if nothing
    else in the document does.
    """
    chunk_count = chunk_and_index_document(document_id, filename, text)
    collection = _get_collection() if chunk_count else None

    results: list[ExtractionCandidate] = []
    for term in key_terms:
        label = term["label"]
        aliases = term.get("aliases", [])
        data_type = term.get("data_type", "text")
        requires_typed_match = data_type in _STRICT_TYPES

        value, confidence, method = "", 0.0, "not_found"
        untyped_fallback: tuple[str, float] | None = None

        if collection is not None:
            for chunk_text, distance in _best_chunks_for_term(collection, document_id, label, aliases, data_type):
                candidate_value, candidate_confidence, _, typed_ok = extraction.match_value_in_text(
                    chunk_text, label, aliases, data_type
                )
                if not candidate_value:
                    continue

                if typed_ok or not requires_typed_match:
                    value, confidence, method = candidate_value, candidate_confidence, "semantic"
                    if distance > _LOW_RELEVANCE_DISTANCE:
                        confidence = min(confidence, 0.5)
                    break

                # A chunk mentioned the term but didn't yield a value in the
                # expected format (e.g. "currency" with no number in it) --
                # remember it in case nothing better turns up, but keep
                # searching the rest of the candidate chunks first.
                if untyped_fallback is None:
                    untyped_fallback = (candidate_value, candidate_confidence)

            if not value and untyped_fallback:
                value, confidence = untyped_fallback
                confidence = min(confidence, _UNTYPED_MATCH_CONFIDENCE_CAP)
                method = "semantic"

        if not value:
            # No index, or nothing in it panned out -- fall back to a direct
            # regex search over the whole document, still respecting the
            # expected type before accepting an untyped match.
            fallback_value, fallback_confidence, _, typed_ok = extraction.match_value_in_text(text, label, aliases, data_type)
            if fallback_value and requires_typed_match and not typed_ok:
                fallback_confidence = min(fallback_confidence, _UNTYPED_MATCH_CONFIDENCE_CAP)
            value, confidence = fallback_value, fallback_confidence
            method = "regex_fallback" if value else "not_found"

        results.append(ExtractionCandidate(term["id"], label, value, round(max(0.0, min(confidence, 0.99)), 2), method))

    return results
