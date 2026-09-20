export interface DealSummary {
  id: string;
  borrower_name: string;
  deal_name: string;
  industry: string;
  stage: string;
  risk_rating: string;
  watchlist: boolean;
  covenant_status: string;
  commitment: number;
  outstanding_balance: number;
  latest_borrowing_base: number;
  latest_availability: number;
  created_at: string;
}

export interface DealCreate {
  borrower_name: string;
  deal_name: string;
  industry: string;
  commitment: number;
  created_by: string;
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

// ---- document reference view ----

export type PageSource = 'pdf' | 'docx_markers' | 'none';

export interface Evidence {
  evidence_id: string;
  rank: number;
  used: boolean;
  outcome: 'selected' | 'selected_untyped' | 'selected_fallback' | 'no_value_in_chunk' | 'type_mismatch' | 'not_examined';
  distance: number | null;
  similarity: number | null;
  page: number | null;
  page_source: PageSource;
  section: string;
  granularity: 'paragraph' | 'line';
  text: string;
  value_text: string;
  image_url: string;
  page_image_url: string;
}

export interface ReferenceField {
  field_id: string;
  label: string;
  data_type: KeyTerm['data_type'];
  value: string;
  original_value: string;
  edited: boolean;
  confidence: number;
  match_method: string;
  status: ExtractedField['status'];
  reviewed_by: string;
  grounded: boolean | null;
  evidence: Evidence[];
}

export interface ReferenceSection {
  title: string;
  page_start: number | null;
  page_end: number | null;
  chunk_count: number;
  field_labels: string[];
}

export interface ReferenceDocument {
  id: string;
  filename: string;
  file_kind: 'pdf' | 'docx' | 'txt';
  document_type: string;
  deal_id: string | null;
  deal_name: string;
  status: DocumentRecord['status'];
  uploaded_at: string;
  page_count: number | null;
  page_source: PageSource;
  has_evidence: boolean;
  original_available: boolean;
}

export interface DocumentReference {
  document: ReferenceDocument;
  sections: ReferenceSection[];
  fields: ReferenceField[];
}

// ---- agent eval view ----

export type AgentKind = 'document_intake' | 'stage_agent' | 'wiki' | 'borrowing_base';

export interface AgentCall {
  id: string;
  created_at: string;
  agent_kind: AgentKind;
  agent_name: string;
  mode: 'llm' | 'rule_based' | 'retrieval' | 'deterministic';
  status: 'success' | 'fallback' | 'error';
  error: string;
  model: string;
  deal_id: string | null;
  deal_name: string;
  document_id: string | null;
  stage_id: string;
  triggered_by: string;
  input_summary: string;
  latency_ms: number;
  retrieval_ms: number | null;
  llm_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
  groundedness: number | null;
  context_relevance: number | null;
  answer_relevance: number | null;
  accuracy: number | null;
  accuracy_basis: string;
  human_rating: 'up' | 'down' | null;
  rated_by: string;
  rated_at: string | null;
}

export interface SentenceSupport {
  sentence: string;
  support: number;
  supported: boolean;
  closest_context: string;
}

export interface IntakeFieldEval {
  field_id: string;
  label: string;
  original_value: string;
  value: string;
  status: ExtractedField['status'];
  confidence: number;
  match_method: string;
  page: number | null;
  section: string;
  grounded: boolean | null;
}

export interface ProposedChangeEval {
  id: string;
  field_path: string;
  new_value: string;
  status: ChangeStatus;
  guardrail_status: GuardrailStatus;
}

export interface AgentCallDetail extends AgentCall {
  output_summary: string;
  human_notes: string;
  details: {
    sentence_support?: SentenceSupport[];
    retrieval?: { source: string; title: string; distance: number }[];
    stop_reason?: string | null;
    eval_error?: string;
    [key: string]: unknown;
  };
  intake_fields: IntakeFieldEval[];
  proposed_changes: ProposedChangeEval[];
}

export interface AgentAggregate {
  calls: number;
  success: number;
  fallback: number;
  error: number;
  llm_calls: number;
  latency_avg_ms: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  avg_tokens_per_llm_call: number | null;
  groundedness: number | null;
  context_relevance: number | null;
  answer_relevance: number | null;
  accuracy: number | null;
  accuracy_evaluated: number;
  thumbs_up: number;
  thumbs_down: number;
}

export interface AgentGroupAggregate extends AgentAggregate {
  agent_kind: AgentKind;
  agent_name: string;
}

export interface AgentSummary {
  overall: AgentAggregate;
  by_agent: AgentGroupAggregate[];
}

export interface AgentCallFilters {
  agent_kind?: string;
  mode?: string;
  status?: string;
  deal_id?: string;
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
