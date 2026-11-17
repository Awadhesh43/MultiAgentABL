import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe, PercentPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { Session } from '../../core/session';
import { AgentCall, AgentCallDetail, AgentKind, AgentSummary, SentenceSupport } from '../../core/models';
import { MetricBar } from '../../shared/metric-bar/metric-bar';
import { StatusBadge } from '../../shared/status-badge/status-badge';

const KIND_LABELS: Record<AgentKind, string> = {
  document_intake: 'Document Intake',
  stage_agent: 'Stage agent',
  wiki: 'ABL Wiki',
  borrowing_base: 'Borrowing Base',
};

const MODE_LABELS: Record<AgentCall['mode'], string> = {
  llm: 'LLM',
  rule_based: 'Rule-based',
  retrieval: 'Retrieval only',
  deterministic: 'Deterministic',
};

const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }));
const MODE_OPTIONS = Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label }));

@Component({
  selector: 'app-agent-evals',
  imports: [
    RouterLink, FormsModule, MatCardModule, MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatProgressSpinnerModule, MatTooltipModule, DatePipe, DecimalPipe, PercentPipe, MetricBar,
    StatusBadge,
  ],
  templateUrl: './agent-evals.html',
  styleUrl: './agent-evals.scss',
})
export class AgentEvals implements OnInit {
  private api = inject(Api);
  private snack = inject(MatSnackBar);
  protected session = inject(Session);

  protected readonly kindOptions = KIND_OPTIONS;
  protected readonly modeOptions = MODE_OPTIONS;

  protected loading = signal(true);
  protected summary = signal<AgentSummary | null>(null);
  protected calls = signal<AgentCall[]>([]);

  protected kindFilter = signal('');
  protected modeFilter = signal('');
  protected statusFilter = signal('');

  protected expandedId = signal<string | null>(null);
  protected detail = signal<AgentCallDetail | null>(null);
  protected detailLoading = signal(false);
  protected notes = signal('');
  protected saving = signal(false);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    forkJoin({
      summary: this.api.getAgentSummary({ agent_kind: this.kindFilter() }),
      calls: this.api.listAgentCalls({ agent_kind: this.kindFilter(), mode: this.modeFilter(), status: this.statusFilter() }),
    }).subscribe({
      next: ({ summary, calls }) => {
        this.summary.set(summary);
        this.calls.set(calls);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  setFilter(which: 'kind' | 'mode' | 'status', value: string): void {
    ({ kind: this.kindFilter, mode: this.modeFilter, status: this.statusFilter })[which].set(value);
    this.expandedId.set(null);
    this.reload();
  }

  toggle(call: AgentCall): void {
    if (this.expandedId() === call.id) {
      this.expandedId.set(null);
      return;
    }
    this.expandedId.set(call.id);
    this.loadDetail(call.id);
  }

  private loadDetail(id: string): void {
    this.detail.set(null);
    this.detailLoading.set(true);
    this.api.getAgentCall(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.notes.set(d.human_notes);
        this.detailLoading.set(false);
      },
      error: () => this.detailLoading.set(false),
    });
  }

  rate(call: AgentCallDetail, rating: 'up' | 'down'): void {
    const next = call.human_rating === rating ? null : rating; // clicking the active rating clears it
    this.saving.set(true);
    this.api.rateAgentCall(call.id, next, this.notes(), this.session.name()).subscribe({
      next: () => {
        this.saving.set(false);
        this.snack.open(next ? 'Rating saved and added to the audit trail.' : 'Rating cleared.', 'Dismiss', { duration: 3000 });
        this.reload();
        this.loadDetail(call.id);
      },
      error: () => this.saving.set(false),
    });
  }

  // --- formatting helpers ---

  kindLabel(kind: AgentKind): string {
    return KIND_LABELS[kind];
  }

  modeLabel(mode: AgentCall['mode']): string {
    return MODE_LABELS[mode];
  }

  ms(value: number | null): string {
    if (value === null || value === undefined) return '—';
    return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(1)} s`;
  }

  tokens(call: AgentCall): string {
    if (call.input_tokens === null) return '—';
    return `${call.input_tokens.toLocaleString()} / ${(call.output_tokens ?? 0).toLocaleString()}`;
  }

  /** A numeric entry from a call's free-form details, 0 if absent. */
  detailNum(call: AgentCallDetail, key: string): number {
    return Number(call.details[key] ?? 0);
  }

  retrievalOf(call: AgentCallDetail): { source: string; title: string; distance: number }[] {
    return call.details.retrieval ?? [];
  }

  sentencesOf(call: AgentCallDetail): SentenceSupport[] {
    return call.details.sentence_support ?? [];
  }

  otherMs(call: AgentCallDetail): number {
    return Math.max(0, call.latency_ms - (call.retrieval_ms ?? 0) - (call.llm_ms ?? 0));
  }

  similarity(distance: number): number {
    return Math.max(0, Math.min(1, 1 - distance / 2));
  }

  successRate(s: { calls: number; success: number }): number | null {
    return s.calls ? s.success / s.calls : null;
  }

  ratedLabel(call: AgentCall): string {
    return call.human_rating === 'up' ? 'thumbs up' : call.human_rating === 'down' ? 'thumbs down' : '';
  }
}
