"""The Document Intake Agent.

Runs whenever the API receives an "upload document" command (see
routers/documents.py -- upload_document), and is responsible for turning a
document's raw extracted text into structured key-term values ready for
human review.

Unlike the stage agents in recommendations.py, this agent doesn't branch on
whether ANTHROPIC_API_KEY is configured: extracting key terms from a
document isn't a judgment call the way "should this credit migrate to the
watchlist" is -- there's exactly one tool to reach for and exactly one
correct way to call it, so every user gets the same grounded,
semantic-search-backed extraction (semantic_extraction.run_extraction)
regardless of whether an LLM is configured.
"""
from __future__ import annotations

from .document_structure import ExtractedDocument, from_plain_text
from .extraction import IntakeResult
from .semantic_extraction import run_extraction


def run(document_id: str, filename: str, document: ExtractedDocument | str, key_terms: list[dict]) -> IntakeResult:
    """Handles one 'upload document' command: calls the semantic key-term
    extraction tool, scoped to this document's own chunks. Returns one
    ExtractionCandidate per requested key term for the caller to persist,
    plus the chunks (with page/section) and per-term evidence behind them.

    `document` is the ExtractedDocument from document_structure.extract_document;
    plain text is accepted too, for sources that have no pages or headings."""
    if isinstance(document, str):
        document = from_plain_text(document)
    return run_extraction(document_id, filename, document, key_terms)
