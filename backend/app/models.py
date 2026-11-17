"""SQLAlchemy ORM models -- the system of record for the web platform."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    borrower_name: Mapped[str] = mapped_column(String)
    deal_name: Mapped[str] = mapped_column(String, default="")
    industry: Mapped[str] = mapped_column(String)
    naics: Mapped[str] = mapped_column(String, default="")
    hq: Mapped[str] = mapped_column(String, default="")
    sponsor: Mapped[str] = mapped_column(String, default="")

    facility_type: Mapped[str] = mapped_column(String, default="Senior secured ABL revolver")
    commitment: Mapped[float] = mapped_column(Float)
    closing_date: Mapped[str] = mapped_column(String, default="")
    maturity_date: Mapped[str] = mapped_column(String, default="")

    ar_advance_rate: Mapped[float] = mapped_column(Float, default=0.85)
    inventory_advance_rate_nolv: Mapped[float] = mapped_column(Float, default=0.85)
    inventory_cost_cap_pct: Mapped[float] = mapped_column(Float, default=0.60)
    dilution_threshold_pct: Mapped[float] = mapped_column(Float, default=0.05)
    excess_availability_trigger_pct: Mapped[float] = mapped_column(Float, default=0.10)
    excess_availability_trigger_floor: Mapped[float] = mapped_column(Float, default=2_000_000)
    fccr_minimum: Mapped[float] = mapped_column(Float, default=1.10)

    stage: Mapped[str] = mapped_column(String, default="origination")
    risk_rating: Mapped[str] = mapped_column(String, default="Pass")
    watchlist: Mapped[bool] = mapped_column(Boolean, default=False)
    covenant_status: Mapped[str] = mapped_column(String, default="not_yet_tested")

    outstanding_balance: Mapped[float] = mapped_column(Float, default=0.0)
    letters_of_credit: Mapped[float] = mapped_column(Float, default=0.0)
    latest_borrowing_base: Mapped[float] = mapped_column(Float, default=0.0)
    latest_availability: Mapped[float] = mapped_column(Float, default=0.0)

    trailing_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    trailing_ebitda: Mapped[float] = mapped_column(Float, default=0.0)
    unfinanced_capex: Mapped[float] = mapped_column(Float, default=0.0)
    cash_taxes_paid: Mapped[float] = mapped_column(Float, default=0.0)
    distributions: Mapped[float] = mapped_column(Float, default=0.0)
    scheduled_debt_service: Mapped[float] = mapped_column(Float, default=0.0)
    annual_rent_and_leases: Mapped[float] = mapped_column(Float, default=0.0)

    authority_level: Mapped[str] = mapped_column(String, default="Credit Officer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    stage_events: Mapped[list["StageEvent"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    bbcs: Mapped[list["BorrowingBaseCertificate"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    pending_changes: Mapped[list["PendingChange"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="deal", cascade="all, delete-orphan")


class StageEvent(Base):
    """One row per lifecycle stage the deal has entered -- drives the timeline UI."""
    __tablename__ = "stage_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"))
    stage: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="in_progress")  # completed | in_progress | pending | blocked
    notes: Mapped[str] = mapped_column(Text, default="")
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    deal: Mapped[Deal] = relationship(back_populates="stage_events")


class BorrowingBaseCertificate(Base):
    __tablename__ = "borrowing_base_certificates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"))
    period_end: Mapped[str] = mapped_column(String)
    gross_ar: Mapped[float] = mapped_column(Float)
    eligible_ar: Mapped[float] = mapped_column(Float)
    ar_availability: Mapped[float] = mapped_column(Float)
    inventory_at_cost: Mapped[float] = mapped_column(Float)
    eligible_inventory_at_cost: Mapped[float] = mapped_column(Float)
    inventory_availability: Mapped[float] = mapped_column(Float)
    dilution_pct: Mapped[float] = mapped_column(Float)
    dilution_reserve: Mapped[float] = mapped_column(Float)
    rent_reserve: Mapped[float] = mapped_column(Float, default=0.0)
    borrowing_base: Mapped[float] = mapped_column(Float)
    outstanding_balance: Mapped[float] = mapped_column(Float)
    letters_of_credit: Mapped[float] = mapped_column(Float, default=0.0)
    availability: Mapped[float] = mapped_column(Float)
    cash_dominion_active: Mapped[bool] = mapped_column(Boolean, default=False)
    fccr_tested: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    deal: Mapped[Deal] = relationship(back_populates="bbcs")


class PendingChange(Base):
    """The HITL queue. Nothing here has been applied to the Deal row until
    status flips to 'approved' and the orchestration layer writes it."""
    __tablename__ = "pending_changes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"))
    stage: Mapped[str] = mapped_column(String)
    change_type: Mapped[str] = mapped_column(String)  # field_update | risk_rating | watchlist | draw_funding | covenant_result | document_intake
    field_path: Mapped[str] = mapped_column(String)
    old_value: Mapped[str] = mapped_column(String, default="")
    new_value: Mapped[str] = mapped_column(String)
    rationale: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[str] = mapped_column(String)  # agent name or human name

    guardrail_status: Mapped[str] = mapped_column(String, default="pass")  # pass | warn | requires_elevated_approval | blocked
    guardrail_notes: Mapped[str] = mapped_column(Text, default="")
    required_authority: Mapped[str] = mapped_column(String, default="")

    status: Mapped[str] = mapped_column(String, default="pending")  # pending | approved | rejected
    decided_by: Mapped[str] = mapped_column(String, default="")
    decided_role: Mapped[str] = mapped_column(String, default="")
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    override_used: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    deal: Mapped[Deal] = relationship(back_populates="pending_changes")


class AuditLogEntry(Base):
    """Append-only, hash-chained. Rows are never updated or deleted by the API."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, default=_now_iso)
    event_type: Mapped[str] = mapped_column(String)
    deal_id: Mapped[str] = mapped_column(String, default="")
    stage: Mapped[str] = mapped_column(String, default="")
    actor: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String)


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    key_terms: Mapped[list["KeyTerm"]] = relationship(back_populates="document_type", cascade="all, delete-orphan")


class KeyTerm(Base):
    """One field the extractor should look for in a given document type.
    Users can add new terms to this list from the UI."""
    __tablename__ = "key_terms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    document_type_id: Mapped[str] = mapped_column(ForeignKey("document_types.id"))
    label: Mapped[str] = mapped_column(String)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    data_type: Mapped[str] = mapped_column(String, default="text")  # number | percent | date | text | currency
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    document_type: Mapped[DocumentType] = relationship(back_populates="key_terms")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"), nullable=True)
    document_type_id: Mapped[str] = mapped_column(ForeignKey("document_types.id"))
    filename: Mapped[str] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="processed")  # processed | failed | pending_review
    raw_text_excerpt: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    uploaded_by: Mapped[str] = mapped_column(String, default="demo_user")

    deal: Mapped[Deal | None] = relationship(back_populates="documents")
    document_type: Mapped[DocumentType] = relationship()
    extracted_fields: Mapped[list["ExtractedField"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ExtractedField(Base):
    """One (key term -> value) result from running a document through the
    parser. Stays 'pending_review' until a human confirms or edits it."""
    __tablename__ = "extracted_fields"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    key_term_id: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    extracted_value: Mapped[str] = mapped_column(String, default="")
    # What the agent originally extracted. `extracted_value` is overwritten when
    # a reviewer edits it, so this is what lets the agent eval view measure how
    # often a human had to change the agent's answer. '' on rows that predate it.
    original_value: Mapped[str] = mapped_column(String, default="", server_default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    match_method: Mapped[str] = mapped_column(String, default="regex")
    status: Mapped[str] = mapped_column(String, default="pending_review")  # pending_review | confirmed | rejected
    reviewed_by: Mapped[str] = mapped_column(String, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document: Mapped[Document] = relationship(back_populates="extracted_fields")
    evidence: Mapped[list["FieldEvidence"]] = relationship(
        back_populates="field", cascade="all, delete-orphan", order_by="FieldEvidence.rank",
    )


class DocumentChunk(Base):
    """One retrievable passage of an uploaded document, with where it sits in
    the source (page + section). This is what the reference view shows a human
    when they check where an extracted value came from."""
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)  # same index stored in the Chroma chunk metadata
    text: Mapped[str] = mapped_column(Text)
    granularity: Mapped[str] = mapped_column(String, default="paragraph")  # paragraph | line
    char_start: Mapped[int] = mapped_column(Integer, default=0)  # offset into the document's extracted text
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null when the format has no pages
    # pdf = exact | docx_markers = from Word's saved page breaks, approximate | none = no pagination
    page_source: Mapped[str] = mapped_column(String, default="none")
    section: Mapped[str] = mapped_column(String, default="")  # heading breadcrumb, e.g. "1. ELIGIBLE AR > A/R Advance"

    document: Mapped[Document] = relationship(back_populates="chunks")


class FieldEvidence(Base):
    """Links an extracted field to the chunk(s) the extractor looked at for it.
    rank 0 is the chunk the value was actually taken from (when one was); the
    rest are the other retrieval candidates and why each was passed over."""
    __tablename__ = "field_evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    field_id: Mapped[str] = mapped_column(ForeignKey("extracted_fields.id"))
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id"))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    # selected | selected_untyped | selected_fallback | no_value_in_chunk | type_mismatch | not_examined
    outcome: Mapped[str] = mapped_column(String, default="not_examined")
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)  # Chroma distance; null for regex fallback
    value_text: Mapped[str] = mapped_column(String, default="")  # the raw text in the chunk the value was read from

    field: Mapped[ExtractedField] = relationship(back_populates="evidence")
    chunk: Mapped[DocumentChunk] = relationship()


class AgentCall(Base):
    """One row per agent invocation -- the source for the agent eval view.
    Ids of deals/documents/proposed changes are plain strings (no foreign
    keys) so a call record stays valid on its own."""
    __tablename__ = "agent_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    agent_kind: Mapped[str] = mapped_column(String)  # document_intake | stage_agent | wiki | borrowing_base
    agent_name: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String, default="")  # llm | rule_based | retrieval | deterministic
    status: Mapped[str] = mapped_column(String, default="success")  # success | fallback | error
    error: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String, default="")

    deal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    document_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stage_id: Mapped[str] = mapped_column(String, default="")
    triggered_by: Mapped[str] = mapped_column(String, default="")
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")

    # performance
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # automated quality metrics, 0..1; null means "doesn't apply to this call"
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)

    # explicit human evaluation
    human_rating: Mapped[str | None] = mapped_column(String, nullable=True)  # up | down
    human_notes: Mapped[str] = mapped_column(Text, default="")
    rated_by: Mapped[str] = mapped_column(String, default="")
    rated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    details: Mapped[dict] = mapped_column(JSON, default=dict)
