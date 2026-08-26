export interface DealSummary {
  id: string;
  borrower_name: string;
  industry: string;
  stage: string;
  risk_rating: string;
  watchlist: boolean;
  covenant_status: string;
  commitment: number;
  outstanding_balance: number;
  latest_borrowing_base: number;
  latest_availability: number;
}

export interface DealDetail extends DealSummary {
  naics: string;
  hq: string;
  sponsor: string;
  facility_type: string;
  closing_date: string;
  maturity_date: string;
  ar_advance_rate: number;
  inventory_advance_rate_nolv: number;
  inventory_cost_cap_pct: number;
  dilution_threshold_pct: number;
  excess_availability_trigger_pct: number;
  excess_availability_trigger_floor: number;
  fccr_minimum: number;
  letters_of_credit: number;
  trailing_revenue: number;
  trailing_ebitda: number;
  unfinanced_capex: number;
  cash_taxes_paid: number;
  distributions: number;
  scheduled_debt_service: number;
  annual_rent_and_leases: number;
  authority_level: string;
  created_at: string;
  updated_at: string;
}

export interface StageEvent {
  id: string;
  stage: string;
  status: 'completed' | 'in_progress' | 'pending' | 'blocked';
  notes: string;
  entered_at: string;
  completed_at: string | null;
}

export interface Bbc {
  id: string;
  period_end: string;
  gross_ar: number;
  eligible_ar: number;
  ar_availability: number;
  inventory_at_cost: number;
  eligible_inventory_at_cost: number;
  inventory_availability: number;
  dilution_pct: number;
  dilution_reserve: number;
  rent_reserve: number;
  borrowing_base: number;
  outstanding_balance: number;
  letters_of_credit: number;
  availability: number;
  cash_dominion_active: boolean;
  fccr_tested: boolean;
  note: string;
  created_at: string;
}

export interface BbcSubmission {
  period_end: string;
  gross_ar: number;
  ar_ineligibles: Record<string, number>;
  inventory_at_cost: number;
  ineligible_inventory: number;
  nolv_pct_of_cost: number;
  trailing_gross_sales: number;
  trailing_credits_discounts_writeoffs: number;
  rent_reserve: number;
  requested_draw: number;
  proposed_by: string;
}

export type GuardrailStatus = 'pass' | 'warn' | 'requires_elevated_approval' | 'blocked';
export type ChangeStatus = 'pending' | 'approved' | 'rejected';

export interface PendingChange {
  id: string;
  deal_id: string;
  stage: string;
  change_type: string;
  field_path: string;
  old_value: string;
  new_value: string;
  rationale: string;
  proposed_by: string;
  guardrail_status: GuardrailStatus;
  guardrail_notes: string;
  required_authority: string;
  status: ChangeStatus;
  decided_by: string;
  decided_role: string;
  decision_notes: string;
  override_used: boolean;
  created_at: string;
  decided_at: string | null;
}

export interface ApprovalDecision {
  approve: boolean;
  decided_by: string;
  role: string;
  notes: string;
  override: boolean;
}

export interface AuditEntry {
  id: number;
  ts: string;
  event_type: string;
  deal_id: string;
  stage: string;
  actor: string;
  summary: string;
  detail: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface ChainStatus {
  valid: boolean;
  broken_at_id: number | null;
  entry_count: number;
}

export interface KeyTerm {
  id: string;
  label: string;
  aliases: string[];
  data_type: 'text' | 'number' | 'percent' | 'date' | 'currency';
  required: boolean;
  is_default: boolean;
}

export interface DocumentType {
  id: string;
  name: string;
  description: string;
  key_terms: KeyTerm[];
}

export interface ExtractedField {
  id: string;
  key_term_id: string;
  label: string;
  extracted_value: string;
  confidence: number;
  match_method: string;
  status: 'pending_review' | 'confirmed' | 'rejected';
  reviewed_by: string;
  reviewed_at: string | null;
}

export interface SkippedField {
  field_id: string;
  label: string;
  deal_field: string;
  reason: string;
}

export interface ApplyFieldsResponse {
  created: PendingChange[];
  skipped: SkippedField[];
}

export interface DocumentRecord {
  id: string;
  deal_id: string | null;
  document_type_id: string;
  filename: string;
  status: 'processed' | 'failed' | 'pending_review';
  raw_text_excerpt: string;
  uploaded_at: string;
  uploaded_by: string;
  extracted_fields: ExtractedField[];
}

export interface WikiChatResponse {
  answer: string;
  citations: { source: string; title: string }[];
  grounded: boolean;
}

export interface AdvanceStageResponse {
  from_stage: string;
  to_stage: string;
  to_stage_label: string;
}

export interface StageRunResponse {
  stage: string;
  agent_name: string;
  text: string;
  citations: { source: string; title: string }[];
  source: 'llm' | 'rule_based';
  pending_changes: PendingChange[];
}

export const LIFECYCLE_STAGES: { id: string; label: string }[] = [
  { id: 'origination', label: 'Origination' },
  { id: 'underwriting', label: 'Underwriting' },
  { id: 'documentation_closing', label: 'Documentation & Closing' },
  { id: 'boarding', label: 'Boarding' },
  { id: 'borrowing_base', label: 'Servicing & Monitoring' },
  { id: 'field_exam', label: 'Field Exam' },
  { id: 'covenant_compliance', label: 'Covenant Compliance' },
  { id: 'portfolio_risk', label: 'Portfolio Risk' },
  { id: 'renewal_amendment', label: 'Renewal / Amendment' },
];

export const WORKOUT_STAGE = { id: 'special_assets_workout', label: 'Special Assets / Workout' };

export const DEAL_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: 'risk_rating', label: 'Risk rating' },
  { value: 'watchlist', label: 'Watchlist flag' },
  { value: 'covenant_status', label: 'Covenant status' },
  { value: 'outstanding_balance', label: 'Outstanding balance' },
  { value: 'latest_borrowing_base', label: 'Latest borrowing base' },
  { value: 'latest_availability', label: 'Latest availability' },
  { value: 'trailing_ebitda', label: 'Trailing EBITDA' },
  { value: 'trailing_revenue', label: 'Trailing revenue' },
];
