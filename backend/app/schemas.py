from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DealSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    borrower_name: str
    deal_name: str
    industry: str
    stage: str
    risk_rating: str
    watchlist: bool
    covenant_status: str
    commitment: float
    outstanding_balance: float
    latest_borrowing_base: float
    latest_availability: float
    created_at: datetime


class DealCreate(BaseModel):
    borrower_name: str
    deal_name: str
    industry: str = ""
    commitment: float
    created_by: str = "demo_user"


class DealDetail(DealSummary):
    naics: str
    hq: str
    sponsor: str
    facility_type: str
    closing_date: str
    maturity_date: str
    ar_advance_rate: float
    inventory_advance_rate_nolv: float
    inventory_cost_cap_pct: float
    dilution_threshold_pct: float
    excess_availability_trigger_pct: float
    excess_availability_trigger_floor: float
    fccr_minimum: float
    letters_of_credit: float
    trailing_revenue: float
    trailing_ebitda: float
    unfinanced_capex: float
    cash_taxes_paid: float
    distributions: float
    scheduled_debt_service: float
    annual_rent_and_leases: float
    authority_level: str
    updated_at: datetime


class StageEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stage: str
    status: str
    notes: str
    entered_at: datetime
    completed_at: datetime | None = None


class BBCOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    period_end: str
    gross_ar: float
    eligible_ar: float
    ar_availability: float
    inventory_at_cost: float
    eligible_inventory_at_cost: float
    inventory_availability: float
    dilution_pct: float
    dilution_reserve: float
    rent_reserve: float
    borrowing_base: float
    outstanding_balance: float
    letters_of_credit: float
    availability: float
    cash_dominion_active: bool
    fccr_tested: bool
    note: str
    created_at: datetime


class BBCSubmissionIn(BaseModel):
    period_end: str
    gross_ar: float
    ar_ineligibles: dict[str, float]
    inventory_at_cost: float
    ineligible_inventory: float
    nolv_pct_of_cost: float
    trailing_gross_sales: float
    trailing_credits_discounts_writeoffs: float
    rent_reserve: float = 0.0
    requested_draw: float = 0.0
    proposed_by: str = "Borrowing Base Agent"


class PendingChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    deal_id: str
    stage: str
    change_type: str
    field_path: str
    old_value: str
    new_value: str
    rationale: str
    proposed_by: str
    guardrail_status: str
    guardrail_notes: str
    required_authority: str
    status: str
    decided_by: str
    decided_role: str
    decision_notes: str
    override_used: bool
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalDecision(BaseModel):
    approve: bool
    decided_by: str
    role: str
    notes: str = ""
    override: bool = False


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    event_type: str
    deal_id: str
    stage: str
    actor: str
    summary: str
    detail: dict
    prev_hash: str
    hash: str


class ChainStatus(BaseModel):
    valid: bool
    broken_at_id: int | None
    entry_count: int


class KeyTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    aliases: list[str]
    data_type: str
    required: bool
    is_default: bool


class KeyTermCreate(BaseModel):
    label: str
    aliases: list[str] = []
    data_type: str = "text"
    required: bool = True


class KeyTermAliasUpdate(BaseModel):
    """Deliberately has no `label` field -- a key term's label is fixed once
    created; editing a term can only append new aliases to it."""
    aliases_to_add: list[str]


class DocumentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    key_terms: list[KeyTermOut]


class DocumentTypeCreate(BaseModel):
    name: str
    description: str = ""


class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key_term_id: str
    label: str
    extracted_value: str
    confidence: float
    match_method: str
    status: str
    reviewed_by: str
    reviewed_at: datetime | None = None


class ExtractedFieldUpdate(BaseModel):
    value: str
    reviewed_by: str
    confirm: bool = True


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    deal_id: str | None
    document_type_id: str
    filename: str
    status: str
    raw_text_excerpt: str
    uploaded_at: datetime
    uploaded_by: str
    extracted_fields: list[ExtractedFieldOut]


class ApplyFieldsRequest(BaseModel):
    field_ids: list[str]
    deal_field_map: dict[str, str] = {}
    proposed_by: str = "Document Intake"


class SkippedField(BaseModel):
    field_id: str
    label: str
    deal_field: str
    reason: str


class ApplyFieldsResponse(BaseModel):
    created: list[PendingChangeOut]
    skipped: list[SkippedField]


class WikiChatRequest(BaseModel):
    question: str


class WikiChatResponse(BaseModel):
    answer: str
    citations: list[dict]
    grounded: bool


class StageRunRequest(BaseModel):
    extra_context: str = ""


class StageRunResponse(BaseModel):
    stage: str
    agent_name: str
    text: str
    citations: list[dict]
    source: str  # "llm" | "rule_based"
    pending_changes: list[PendingChangeOut]


class AdvanceStageRequest(BaseModel):
    decided_by: str


class AdvanceStageResponse(BaseModel):
    from_stage: str
    to_stage: str
    to_stage_label: str


# ---- document reference view -------------------------------------------------------------

class EvidenceOut(BaseModel):
    evidence_id: str
    rank: int
    used: bool
    outcome: str
    distance: float | None
    similarity: float | None  # cosine similarity of the chunk to the key term's search, 0..1
    page: int | None
    page_source: str  # pdf (exact) | docx_markers (approximate) | none
    section: str
    granularity: str
    text: str
    value_text: str  # the raw text in the chunk the value was read from
    image_url: str
    page_image_url: str


class ReferenceFieldOut(BaseModel):
    field_id: str
    label: str
    data_type: str
    value: str
    original_value: str  # what the agent extracted, before any reviewer edit
    edited: bool
    confidence: float
    match_method: str
    status: str
    reviewed_by: str
    grounded: bool | None  # value found in the passage it was read from; None if there is no source passage
    evidence: list[EvidenceOut]


class SectionOut(BaseModel):
    title: str  # heading trail, levels joined with " › " (empty for text before the first heading)
    page_start: int | None
    page_end: int | None
    chunk_count: int
    field_labels: list[str]  # key terms whose value was read from this section


class ReferenceDocumentOut(BaseModel):
    id: str
    filename: str
    file_kind: str  # pdf | docx | txt
    document_type: str
    deal_id: str | None
    deal_name: str
    status: str
    uploaded_at: datetime
    page_count: int | None
    page_source: str
    has_evidence: bool
    original_available: bool


class DocumentReferenceOut(BaseModel):
    document: ReferenceDocumentOut
    sections: list[SectionOut]
    fields: list[ReferenceFieldOut]


# ---- agent eval view ---------------------------------------------------------------------------

class AgentCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    agent_kind: str
    agent_name: str
    mode: str
    status: str
    error: str
    model: str
    deal_id: str | None
    deal_name: str = ""
    document_id: str | None
    stage_id: str
    triggered_by: str
    input_summary: str
    latency_ms: float
    retrieval_ms: float | None
    llm_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    groundedness: float | None
    context_relevance: float | None
    answer_relevance: float | None
    accuracy: float | None = None
    accuracy_basis: str = ""
    human_rating: str | None
    rated_by: str
    rated_at: datetime | None


class IntakeFieldEval(BaseModel):
    field_id: str
    label: str
    original_value: str
    value: str
    status: str
    confidence: float
    match_method: str
    page: int | None
    section: str
    grounded: bool | None


class ProposedChangeEval(BaseModel):
    id: str
    field_path: str
    new_value: str
    status: str
    guardrail_status: str


class AgentCallDetailOut(AgentCallOut):
    output_summary: str
    human_notes: str
    details: dict
    intake_fields: list[IntakeFieldEval] = []
    proposed_changes: list[ProposedChangeEval] = []


class AgentAggregate(BaseModel):
    calls: int
    success: int
    fallback: int
    error: int
    llm_calls: int
    latency_avg_ms: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    input_tokens: int
    output_tokens: int
    avg_tokens_per_llm_call: int | None
    groundedness: float | None
    context_relevance: float | None
    answer_relevance: float | None
    accuracy: float | None
    accuracy_evaluated: int
    thumbs_up: int
    thumbs_down: int


class AgentGroupAggregate(AgentAggregate):
    agent_kind: str
    agent_name: str


class AgentSummaryOut(BaseModel):
    overall: AgentAggregate
    by_agent: list[AgentGroupAggregate]


class AgentRatingIn(BaseModel):
    rating: str | None  # "up" | "down" | null to clear
    notes: str = ""
    rated_by: str
