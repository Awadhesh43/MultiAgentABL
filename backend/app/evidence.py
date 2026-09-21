"""Persists the provenance the Document Intake Agent produces -- the chunks a
document was split into (with page and section) and, per extracted field, which
chunks were consulted -- so the reference view can show a reviewer exactly where
each value came from.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .extraction import IntakeResult
from .models import DocumentChunk, ExtractedField, FieldEvidence


def attach_evidence(db: Session, document_id: str, result: IntakeResult, fields: list[ExtractedField]) -> None:
    """Stores every chunk of the document (the reference view's outline lists all
    of its sections, not just the ones a value came from), then links each field
    in `fields` (matched to a candidate by key_term_id) to the chunks it looked at.
    """
    rows: dict[int, DocumentChunk] = {}
    for chunk in result.chunks:
        row = DocumentChunk(
            document_id=document_id, chunk_index=chunk.index, text=chunk.text, granularity=chunk.granularity,
            char_start=chunk.char_start, page=chunk.page, page_source=chunk.page_source, section=chunk.section,
        )
        db.add(row)
        rows[chunk.index] = row
    db.flush()  # assigns chunk ids

    by_term = {c.key_term_id: c for c in result.candidates}
    for field in fields:
        candidate = by_term.get(field.key_term_id)
        if not candidate:
            continue
        for rank, ref in enumerate(candidate.evidence):
            db.add(FieldEvidence(
                field_id=field.id, chunk_id=rows[ref.chunk_index].id, rank=rank, used=ref.used,
                outcome=ref.outcome, distance=ref.distance, value_text=ref.value_text,
            ))
