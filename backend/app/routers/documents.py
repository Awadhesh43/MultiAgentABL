from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit, config, crud, document_intake_agent, extraction, guardrails, schemas
from ..db import get_db
from ..models import Document, DocumentType, ExtractedField, KeyTerm, PendingChange

router = APIRouter(prefix="/api", tags=["documents"])

# Deal fields a document field can be mapped onto, grouped by the format the
# extracted value must satisfy before it's allowed onto the HITL queue.
_NUMERIC_DEAL_FIELDS = {
    "outstanding_balance", "latest_borrowing_base", "latest_availability",
    "trailing_ebitda", "trailing_revenue",
}
_BOOLEAN_DEAL_FIELDS = {"watchlist"}
_RATING_DEAL_FIELDS = {"risk_rating"}
_NUMERIC_STRIP_RE = re.compile(r"[^0-9.\-]")
_HAS_LETTER_RE = re.compile(r"[a-z]", re.IGNORECASE)


def _normalize_for_deal_field(field_path: str, raw_value: str) -> tuple[str | None, str]:
    """Returns (normalized_value, reason). normalized_value is None when the
    raw extracted value is empty or doesn't match the target field's expected
    format -- callers should skip staging a change in that case."""
    value = (raw_value or "").strip()
    if not value:
        return None, "the extracted value is empty"

    if field_path in _NUMERIC_DEAL_FIELDS:
        cleaned = _NUMERIC_STRIP_RE.sub("", value)
        if not cleaned or cleaned in ("-", "."):
            return None, f"'{raw_value}' is not a numeric value"
        try:
            return str(float(cleaned)), ""
        except ValueError:
            return None, f"'{raw_value}' is not a numeric value"

    if field_path in _BOOLEAN_DEAL_FIELDS:
        lowered = value.lower()
        if lowered not in {"true", "false", "yes", "no", "1", "0"}:
            return None, f"'{raw_value}' is not a recognizable true/false value"
        return ("true" if lowered in {"true", "yes", "1"} else "false"), ""

    if field_path in _RATING_DEAL_FIELDS:
        if value not in guardrails.RATING_ORDER:
            return None, f"'{raw_value}' is not one of the recognized risk ratings ({', '.join(guardrails.RATING_ORDER)})"
        return value, ""

    # Free-text deal fields (e.g. covenant_status): require at least one letter, so a
    # stray punctuation-only extraction like "," or "--" isn't treated as valid text.
    if not _HAS_LETTER_RE.search(value):
        return None, f"'{raw_value}' does not contain any letters"
    return value, ""


# ---- document types & key terms -------------------------------------------------

@router.get("/document-types", response_model=list[schemas.DocumentTypeOut])
def list_document_types(db: Session = Depends(get_db)):
    return db.query(DocumentType).order_by(DocumentType.name).all()


@router.post("/document-types", response_model=schemas.DocumentTypeOut)
def create_document_type(body: schemas.DocumentTypeCreate, db: Session = Depends(get_db)):
    if db.query(DocumentType).filter(DocumentType.name == body.name).first():
        raise HTTPException(409, "A document type with this name already exists.")
    doc_type = DocumentType(name=body.name, description=body.description)
    db.add(doc_type)
    db.commit()
    db.refresh(doc_type)
    return doc_type


@router.post("/document-types/{type_id}/key-terms", response_model=schemas.KeyTermOut)
def add_key_term(type_id: str, body: schemas.KeyTermCreate, db: Session = Depends(get_db)):
    doc_type = db.get(DocumentType, type_id)
    if not doc_type:
        raise HTTPException(404, "Document type not found")
    term = KeyTerm(
        document_type_id=type_id, label=body.label, aliases=body.aliases,
        data_type=body.data_type, required=body.required, is_default=False,
    )
    db.add(term)
    audit.append(
        db, event_type="key_term_added", actor="demo_user", summary=f"Added key term '{body.label}' to {doc_type.name}",
        detail={"document_type": doc_type.name, "label": body.label, "data_type": body.data_type},
    )
    db.commit()
    db.refresh(term)
    return term


@router.patch("/document-types/{type_id}/key-terms/{term_id}", response_model=schemas.KeyTermOut)
def add_key_term_aliases(type_id: str, term_id: str, body: schemas.KeyTermAliasUpdate, db: Session = Depends(get_db)):
    """Appends new aliases to an existing key term. The label can never be
    changed here -- KeyTermAliasUpdate has no label field -- and existing
    aliases are never dropped or replaced, only added to (case-insensitive
    de-duplication against what's already on the term)."""
    term = db.get(KeyTerm, term_id)
    if not term or term.document_type_id != type_id:
        raise HTTPException(404, "Key term not found")

    candidates = [a.strip() for a in body.aliases_to_add if a.strip()]
    if not candidates:
        raise HTTPException(400, "Provide at least one alias to add.")

    existing_lower = {a.lower() for a in term.aliases}
    merged = list(term.aliases)
    added = []
    for alias in candidates:
        if alias.lower() not in existing_lower:
            merged.append(alias)
            existing_lower.add(alias.lower())
            added.append(alias)

    if not added:
        raise HTTPException(400, "Every alias provided already exists on this term.")

    term.aliases = merged  # reassign (not in-place mutation) so SQLAlchemy tracks the JSON column change
    audit.append(
        db, event_type="key_term_aliases_added", actor="demo_user",
        summary=f"Added alias(es) {', '.join(added)} to '{term.label}'",
        detail={"document_type_id": type_id, "term_id": term_id, "label": term.label, "added": added},
    )
    db.commit()
    db.refresh(term)
    return term


@router.delete("/document-types/{type_id}/key-terms/{term_id}")
def remove_key_term(type_id: str, term_id: str, db: Session = Depends(get_db)):
    term = db.get(KeyTerm, term_id)
    if not term or term.document_type_id != type_id:
        raise HTTPException(404, "Key term not found")
    if term.is_default:
        raise HTTPException(400, "Default key terms can't be removed, only added to.")
    db.delete(term)
    db.commit()
    return {"status": "deleted"}


# ---- documents --------------------------------------------------------------------

@router.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(deal_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Document)
    if deal_id:
        q = q.filter(Document.deal_id == deal_id)
    return q.order_by(Document.uploaded_at.desc()).all()


@router.get("/documents/{doc_id}", response_model=schemas.DocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/documents/upload", response_model=schemas.DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    document_type_id: str = Form(...),
    deal_id: str | None = Form(None),
    uploaded_by: str = Form("demo_user"),
    db: Session = Depends(get_db),
):
    doc_type = db.get(DocumentType, document_type_id)
    if not doc_type:
        raise HTTPException(404, "Document type not found")
    if deal_id:
        crud.get_deal_or_404(db, deal_id)

    content = await file.read()
    dest = config.UPLOAD_DIR / f"{datetime.now(timezone.utc).timestamp():.0f}_{file.filename}"
    dest.write_bytes(content)

    try:
        text = extraction.extract_text(file.filename, content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not parse file: {exc}")

    key_terms = [
        {"id": t.id, "label": t.label, "aliases": t.aliases, "data_type": t.data_type}
        for t in doc_type.key_terms
    ]

    doc = Document(
        deal_id=deal_id, document_type_id=document_type_id, filename=file.filename,
        file_path=str(dest), raw_text_excerpt=text[:3000], uploaded_by=uploaded_by,
        status="pending_review",
    )
    db.add(doc)
    db.flush()  # assigns doc.id, which scopes the semantic chunk search below

    candidates = document_intake_agent.run(doc.id, file.filename, text, key_terms)

    for c in candidates:
        db.add(ExtractedField(
            document_id=doc.id, key_term_id=c.key_term_id, label=c.label,
            extracted_value=c.value, confidence=c.confidence, match_method=c.match_method,
            status="pending_review",
        ))

    found = sum(1 for c in candidates if c.value)
    method_counts: dict[str, int] = {}
    for c in candidates:
        method_counts[c.match_method] = method_counts.get(c.match_method, 0) + 1
    audit.append(
        db, event_type="document_uploaded", actor=uploaded_by, deal_id=deal_id or "",
        summary=f"Uploaded {file.filename} as {doc_type.name}: {found}/{len(candidates)} fields extracted",
        detail={"document_id": doc.id, "document_type": doc_type.name, "extraction_methods": method_counts},
    )

    db.commit()
    db.refresh(doc)
    return doc


@router.patch("/documents/{doc_id}/fields/{field_id}", response_model=schemas.ExtractedFieldOut)
def review_field(doc_id: str, field_id: str, body: schemas.ExtractedFieldUpdate, db: Session = Depends(get_db)):
    field = db.get(ExtractedField, field_id)
    if not field or field.document_id != doc_id:
        raise HTTPException(404, "Extracted field not found")

    field.extracted_value = body.value
    field.status = "confirmed" if body.confirm else "rejected"
    field.reviewed_by = body.reviewed_by
    field.reviewed_at = datetime.now(timezone.utc)
    db.flush()

    doc = db.get(Document, doc_id)
    remaining = (
        db.query(ExtractedField)
        .filter(ExtractedField.document_id == doc_id, ExtractedField.status == "pending_review")
        .count()
    )
    if remaining == 0:
        doc.status = "processed"

    audit.append(
        db, event_type="field_reviewed", actor=body.reviewed_by, deal_id=doc.deal_id or "",
        summary=f"{field.label} -> '{field.extracted_value}' ({field.status})",
        detail={"document_id": doc_id, "field_id": field_id},
    )
    db.commit()
    db.refresh(field)
    return field


@router.post("/documents/{doc_id}/apply-to-deal", response_model=schemas.ApplyFieldsResponse)
def apply_to_deal(doc_id: str, body: schemas.ApplyFieldsRequest, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.deal_id:
        raise HTTPException(400, "This document isn't linked to a deal, so nothing can be applied.")
    deal = crud.get_deal_or_404(db, doc.deal_id)

    created: list[PendingChange] = []
    skipped: list[schemas.SkippedField] = []

    for field_id in body.field_ids:
        field = db.get(ExtractedField, field_id)
        if not field or field.document_id != doc_id or field.status != "confirmed":
            continue
        deal_field = body.deal_field_map.get(field_id)
        if not deal_field:
            continue

        normalized_value, reason = _normalize_for_deal_field(deal_field, field.extracted_value)
        if normalized_value is None:
            skipped.append(schemas.SkippedField(field_id=field_id, label=field.label, deal_field=deal_field, reason=reason))
            continue

        change = crud.create_pending_change(
            db, deal, stage="Document Intake", change_type="document_intake", field_path=deal_field,
            new_value=normalized_value, proposed_by=body.proposed_by,
            rationale=f"Extracted from '{doc.filename}' ({field.label}), confirmed at {field.confidence:.0%} model confidence by {field.reviewed_by or 'reviewer'}.",
            context={"confidence": field.confidence},
        )
        created.append(change)

    if skipped:
        audit.append(
            db, event_type="document_intake_fields_skipped", actor=body.proposed_by, deal_id=deal.id,
            stage="Document Intake",
            summary=f"Skipped {len(skipped)} field(s) from '{doc.filename}' -- empty or format mismatch",
            detail={"skipped": [s.model_dump() for s in skipped]},
        )

    db.commit()
    return schemas.ApplyFieldsResponse(created=created, skipped=skipped)
