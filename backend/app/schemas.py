from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DealSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    borrower_name: str
    industry: str
    stage: str
    risk_rating: str
    watchlist: bool
    covenant_status: str
    commitment: float
    outstanding_balance: float
    latest_borrowing_base: float
    latest_availability: float


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
    created_at: datetime
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
