"""The document reference view: where each extracted value came from.

For every key term a reviewer sees the chunk the value was read from, its page
and section, a screenshot of that passage, and the other chunks that were
considered. This is what a human uses to judge whether the Document Intake
Agent got it right.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import agent_eval, document_structure, evidence_render, schemas
from ..db import get_db
from ..document_structure import SECTION_SEP
from ..models import Deal, Document, DocumentChunk, ExtractedField, FieldEvidence, KeyTerm

router = APIRouter(prefix="/api/documents", tags=["reference"])

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
}


def _file_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix if suffix in ("pdf", "docx") else "txt"


def _original(doc: Document) -> Path | None:
    if not doc.file_path:
        return None
    path = Path(doc.file_path)
    return path if path.is_file() else None


def _get_document(db: Session, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


def _sections(chunks: list[DocumentChunk], used_by_section: dict[str, list[str]]) -> list[schemas.SectionOut]:
    """One entry per distinct heading trail, in the order each first appears."""
    order: list[str] = []
    groups: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        if chunk.section not in groups:
            order.append(chunk.section)
            groups[chunk.section] = []
        groups[chunk.section].append(chunk)
    out = []
    for section in order:
        pages = [c.page for c in groups[section] if c.page is not None]
        out.append(schemas.SectionOut(
            title=section, page_start=min(pages) if pages else None, page_end=max(pages) if pages else None,
            chunk_count=len(groups[section]), field_labels=used_by_section.get(section, []),
        ))
    return out


@router.get("/{doc_id}/reference", response_model=schemas.DocumentReferenceOut)
def get_reference(doc_id: str, db: Session = Depends(get_db)):
    doc = _get_document(db, doc_id)
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index).all()
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc_id).order_by(ExtractedField.id).all()
    data_types = {t.id: t.data_type for t in db.query(KeyTerm).filter(KeyTerm.id.in_([f.key_term_id for f in fields]))} if fields else {}
    deal = db.get(Deal, doc.deal_id) if doc.deal_id else None

    base = f"/api/documents/{doc_id}/evidence"
    used_by_section: dict[str, list[str]] = {}
    field_out: list[schemas.ReferenceFieldOut] = []
    for f in fields:
        evidence: list[schemas.EvidenceOut] = []
        for ev in f.evidence:
            chunk = ev.chunk
            if ev.used:
                used_by_section.setdefault(chunk.section, []).append(f.label)
            evidence.append(schemas.EvidenceOut(
                evidence_id=ev.id, rank=ev.rank, used=ev.used, outcome=ev.outcome, distance=ev.distance,
                similarity=round(agent_eval.similarity_from_distance(ev.distance), 3) if ev.distance is not None else None,
                page=chunk.page, page_source=chunk.page_source, section=chunk.section, granularity=chunk.granularity,
                text=chunk.text, value_text=ev.value_text,
                image_url=f"{base}/{ev.id}/image?view=crop", page_image_url=f"{base}/{ev.id}/image?view=page",
            ))
        source = next((e for e in f.evidence if e.used), None)
        original = f.original_value
        # The value as the agent extracted it, when known (rows from before the
        # agent recorded it have no original, so fall back to the current value).
        machine_value = original or f.extracted_value
        grounded = None
        if source is not None and machine_value:
            grounded = agent_eval.value_supported(machine_value, data_types.get(f.key_term_id, "text"), source.chunk.text)
        field_out.append(schemas.ReferenceFieldOut(
            field_id=f.id, label=f.label, data_type=data_types.get(f.key_term_id, "text"), value=f.extracted_value,
            original_value=machine_value, edited=bool(original) and original.strip() != f.extracted_value.strip(),
            confidence=f.confidence, match_method=f.match_method, status=f.status, reviewed_by=f.reviewed_by,
            grounded=grounded, evidence=evidence,
        ))

    page_source = next((c.page_source for c in chunks if c.page is not None), "none")
    pages = [c.page for c in chunks if c.page is not None]
    return schemas.DocumentReferenceOut(
        document=schemas.ReferenceDocumentOut(
            id=doc.id, filename=doc.filename, file_kind=_file_kind(doc.filename), document_type=doc.document_type.name,
            deal_id=doc.deal_id, deal_name=deal.borrower_name if deal else "", status=doc.status, uploaded_at=doc.uploaded_at,
            page_count=max(pages) if pages else None, page_source=page_source,
            has_evidence=any(f.evidence for f in fields), original_available=_original(doc) is not None,
        ),
        sections=_sections(chunks, used_by_section),
        fields=field_out,
    )


@router.get("/{doc_id}/evidence/{evidence_id}/image")
def get_evidence_image(doc_id: str, evidence_id: str, view: str = Query("crop", pattern="^(crop|page)$"), db: Session = Depends(get_db)):
    doc = _get_document(db, doc_id)
    ev = db.get(FieldEvidence, evidence_id)
    if not ev or ev.field.document_id != doc_id:
        raise HTTPException(404, "Evidence not found")
    chunk = ev.chunk

    out = evidence_render.cache_path(doc_id, ev.id, view)
    if not out.exists():
        original = _original(doc)
        # Surrounding text for the excerpt renderer: re-read the original upload, or
        # (documents seeded from plain text have no file) the stored text.
        context_text = None
        if original is not None:
            try:
                context_text = document_structure.extract_document(doc.filename, original.read_bytes()).text
            except Exception:  # noqa: BLE001 - the excerpt can still show the chunk alone
                context_text = None
        elif doc.raw_text_excerpt:
            context_text = doc.raw_text_excerpt

        page_label = {
            "pdf": f"page {chunk.page}", "docx_markers": f"page ~{chunk.page} (Word's saved pagination, approximate)",
        }.get(chunk.page_source, "no page numbers in this format")
        header = f"Excerpt of {doc.filename} - {page_label} - {chunk.section.replace(SECTION_SEP, ' > ') or 'no section heading'}"
        try:
            evidence_render.render(
                original_path=original, is_pdf=doc.filename.lower().endswith(".pdf"), page=chunk.page,
                chunk_text=chunk.text, chunk_start=chunk.char_start, value_text=ev.value_text,
                context_text=context_text, header=header, view=view, out_path=out,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Could not render this passage: {exc}")
    return FileResponse(out, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{doc_id}/file")
def get_original_file(doc_id: str, db: Session = Depends(get_db)):
    """The document exactly as uploaded, for opening alongside the reference view."""
    doc = _get_document(db, doc_id)
    original = _original(doc)
    if original is None:
        raise HTTPException(404, "The original file isn't available for this document.")
    return FileResponse(
        original, media_type=_MEDIA_TYPES.get(original.suffix.lower(), "application/octet-stream"),
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )
