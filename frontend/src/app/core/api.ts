import { Service, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  AdvanceStageResponse, ApplyFieldsResponse, ApprovalDecision, AuditEntry, Bbc, BbcSubmission, ChainStatus,
  DealDetail, DealSummary, DocumentRecord, DocumentType, ExtractedField, KeyTerm, PendingChange, StageEvent,
  StageRunResponse, WikiChatResponse,
} from './models';

const PRODUCTION_API = 'https://abl-backend-api.vercel.app/api';
const BASE = typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app') ? PRODUCTION_API : '/api';

@Service()
export class Api {
  private http = inject(HttpClient);

  // deals
  listDeals(): Observable<DealSummary[]> {
    return this.http.get<DealSummary[]>(`${BASE}/deals`);
  }
  getDeal(id: string): Observable<DealDetail> {
    return this.http.get<DealDetail>(`${BASE}/deals/${id}`);
  }
  getStageEvents(id: string): Observable<StageEvent[]> {
    return this.http.get<StageEvent[]>(`${BASE}/deals/${id}/stage-events`);
  }
  getBbcHistory(id: string): Observable<Bbc[]> {
    return this.http.get<Bbc[]>(`${BASE}/deals/${id}/bbc`);
  }
  getDealPendingChanges(id: string): Observable<PendingChange[]> {
    return this.http.get<PendingChange[]>(`${BASE}/deals/${id}/pending-changes`);
  }
  submitBbc(id: string, submission: BbcSubmission): Observable<{ bbc: Bbc; calculation: Record<string, unknown>; pending_changes: PendingChange[] }> {
    return this.http.post<{ bbc: Bbc; calculation: Record<string, unknown>; pending_changes: PendingChange[] }>(
      `${BASE}/deals/${id}/bbc/submit`, submission,
    );
  }
  runStage(dealId: string, stageId: string, extraContext = ''): Observable<StageRunResponse> {
    return this.http.post<StageRunResponse>(`${BASE}/deals/${dealId}/stages/${stageId}/run`, { extra_context: extraContext });
  }
  advanceStage(dealId: string, decidedBy: string): Observable<AdvanceStageResponse> {
    return this.http.post<AdvanceStageResponse>(`${BASE}/deals/${dealId}/advance-stage`, { decided_by: decidedBy });
  }

  // HITL
  listPendingChanges(status?: string, dealId?: string): Observable<PendingChange[]> {
    const params: Record<string, string> = {};
    if (status) params['status'] = status;
    if (dealId) params['deal_id'] = dealId;
    return this.http.get<PendingChange[]>(`${BASE}/pending-changes`, { params });
  }
  listRoles(): Observable<string[]> {
    return this.http.get<string[]>(`${BASE}/pending-changes/roles`);
  }
  decide(changeId: string, decision: ApprovalDecision): Observable<PendingChange> {
    return this.http.post<PendingChange>(`${BASE}/pending-changes/${changeId}/decision`, decision);
  }

  // audit
  listAudit(dealId?: string): Observable<AuditEntry[]> {
    const params: Record<string, string> = {};
    if (dealId) params['deal_id'] = dealId;
    return this.http.get<AuditEntry[]>(`${BASE}/audit`, { params });
  }
  verifyChain(): Observable<ChainStatus> {
    return this.http.get<ChainStatus>(`${BASE}/audit/verify`);
  }

  // documents
  listDocumentTypes(): Observable<DocumentType[]> {
    return this.http.get<DocumentType[]>(`${BASE}/document-types`);
  }
  addKeyTerm(typeId: string, term: { label: string; aliases: string[]; data_type: string; required: boolean }): Observable<KeyTerm> {
    return this.http.post<KeyTerm>(`${BASE}/document-types/${typeId}/key-terms`, term);
  }
  addKeyTermAliases(typeId: string, termId: string, aliasesToAdd: string[]): Observable<KeyTerm> {
    return this.http.patch<KeyTerm>(`${BASE}/document-types/${typeId}/key-terms/${termId}`, { aliases_to_add: aliasesToAdd });
  }
  removeKeyTerm(typeId: string, termId: string): Observable<unknown> {
    return this.http.delete(`${BASE}/document-types/${typeId}/key-terms/${termId}`);
  }
  listDocuments(dealId?: string): Observable<DocumentRecord[]> {
    const params: Record<string, string> = {};
    if (dealId) params['deal_id'] = dealId;
    return this.http.get<DocumentRecord[]>(`${BASE}/documents`, { params });
  }
  uploadDocument(file: File, documentTypeId: string, dealId: string | null, uploadedBy: string): Observable<DocumentRecord> {
    const form = new FormData();
    form.append('file', file);
    form.append('document_type_id', documentTypeId);
    if (dealId) form.append('deal_id', dealId);
    form.append('uploaded_by', uploadedBy);
    return this.http.post<DocumentRecord>(`${BASE}/documents/upload`, form);
  }
  reviewField(docId: string, fieldId: string, value: string, reviewedBy: string, confirm: boolean): Observable<ExtractedField> {
    return this.http.patch<ExtractedField>(`${BASE}/documents/${docId}/fields/${fieldId}`, { value, reviewed_by: reviewedBy, confirm });
  }
  applyToDeal(docId: string, fieldIds: string[], dealFieldMap: Record<string, string>, proposedBy: string): Observable<ApplyFieldsResponse> {
    return this.http.post<ApplyFieldsResponse>(`${BASE}/documents/${docId}/apply-to-deal`, {
      field_ids: fieldIds, deal_field_map: dealFieldMap, proposed_by: proposedBy,
    });
  }

  // wiki
  askWiki(question: string): Observable<WikiChatResponse> {
    return this.http.post<WikiChatResponse>(`${BASE}/wiki/chat`, { question });
  }
}
