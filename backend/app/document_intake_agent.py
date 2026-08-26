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
semantic-search-backed extraction (semantic_extraction.extract_key_terms_semantic)
regardless of whether an LLM is configured.
"""
from __future__ import annotations

from .extraction import ExtractionCandidate
from .semantic_extraction import extract_key_terms_semantic


def run(document_id: str, filename: str, text: str, key_terms: list[dict]) -> list[ExtractionCandidate]:
    """Handles one 'upload document' command: calls the semantic key-term
    extraction tool, scoped to this document's own chunks, and returns one
    ExtractionCandidate per requested key term for the caller to persist."""
    return extract_key_terms_semantic(document_id, filename, text, key_terms)
