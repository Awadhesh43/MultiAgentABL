import { Component, OnInit, inject, signal } from '@angular/core';
import { CurrencyPipe, DatePipe, PercentPipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatTabsModule } from '@angular/material/tabs';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatDialog } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCardModule } from '@angular/material/card';
import { MatSnackBar } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { Session } from '../../core/session';
import {
  AuditEntry, Bbc, DealDetail as DealDetailModel, DocumentRecord, LIFECYCLE_STAGES, PendingChange,
  StageEvent, StageRunResponse, WORKOUT_STAGE,
} from '../../core/models';
import { LifecycleTimeline } from '../../shared/lifecycle-timeline/lifecycle-timeline';
import { GuardrailBadge } from '../../shared/guardrail-badge/guardrail-badge';
import { StatusBadge } from '../../shared/status-badge/status-badge';
import { DecisionDialog, DecisionDialogData } from '../../shared/decision-dialog/decision-dialog';

@Component({
  selector: 'app-deal-detail',
  imports: [
    RouterLink, FormsModule, MatTabsModule, MatButtonModule, MatIconModule, MatChipsModule,
    MatFormFieldModule, MatSelectModule, MatInputModule, MatProgressSpinnerModule, MatTableModule,
    MatTooltipModule, MatCardModule, CurrencyPipe, DatePipe, PercentPipe,
    LifecycleTimeline, GuardrailBadge, StatusBadge,
  ],
  templateUrl: './deal-detail.html',
  styleUrl: './deal-detail.scss',
})
export class DealDetail implements OnInit {
  private route = inject(ActivatedRoute);
  private api = inject(Api);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  protected session = inject(Session);

  protected loading = signal(true);
  protected deal = signal<DealDetailModel | null>(null);
  protected stageEvents = signal<StageEvent[]>([]);
  protected bbcHistory = signal<Bbc[]>([]);
  protected pendingChanges = signal<PendingChange[]>([]);
  protected documents = signal<DocumentRecord[]>([]);
  protected auditEntries = signal<AuditEntry[]>([]);
  protected roles = signal<string[]>([]);

  protected readonly allStages = [...LIFECYCLE_STAGES, WORKOUT_STAGE];
  protected selectedStage = signal<string>('origination');
  protected extraContext = signal('');
  protected running = signal(false);
  protected lastRun = signal<StageRunResponse | null>(null);
  protected advancing = signal(false);

  protected readonly bbcColumns = ['period_end', 'gross_ar', 'eligible_ar', 'borrowing_base', 'availability', 'dilution_pct', 'flags'];

  private dealId = '';

  ngOnInit(): void {
    this.dealId = this.route.snapshot.paramMap.get('id')!;
    this.api.listRoles().subscribe((r) => this.roles.set(r));
    this.load();
  }

  load(): void {
    this.loading.set(true);
    forkJoin({
      deal: this.api.getDeal(this.dealId),
      stageEvents: this.api.getStageEvents(this.dealId),
      bbc: this.api.getBbcHistory(this.dealId),
      pending: this.api.getDealPendingChanges(this.dealId),
      documents: this.api.listDocuments(this.dealId),
      audit: this.api.listAudit(this.dealId),
    }).subscribe(({ deal, stageEvents, bbc, pending, documents, audit }) => {
      this.deal.set(deal);
      this.stageEvents.set(stageEvents);
      this.bbcHistory.set(bbc);
      this.pendingChanges.set(pending);
      this.documents.set(documents);
      this.auditEntries.set(audit);
      this.selectedStage.set(deal.stage);
      this.loading.set(false);
    });
  }

  runStage(): void {
    this.running.set(true);
    this.lastRun.set(null);
    this.api.runStage(this.dealId, this.selectedStage(), this.extraContext()).subscribe({
      next: (res) => {
        this.lastRun.set(res);
        this.running.set(false);
        this.load();
      },
      error: () => this.running.set(false),
    });
  }

  decide(change: PendingChange): void {
    const data: DecisionDialogData = { change, roles: this.roles() };
    this.dialog
      .open(DecisionDialog, { data, width: '560px' })
      .afterClosed()
      .subscribe((decision) => {
        if (!decision) return;
        this.api.decide(change.id, decision).subscribe(() => this.load());
      });
  }

  citationLabel(run: StageRunResponse): string {
    return run.citations.map((c) => `${c.title} (${c.source})`).join('; ');
  }

  get pendingOnly(): PendingChange[] {
    return this.pendingChanges().filter((c) => c.status === 'pending');
  }
  get decidedOnly(): PendingChange[] {
    return this.pendingChanges().filter((c) => c.status !== 'pending');
  }

  // --- stage advancement ---

  private get stageIndex(): number {
    return LIFECYCLE_STAGES.findIndex((s) => s.id === this.deal()?.stage);
  }

  get isOnStandardSequence(): boolean {
    return this.stageIndex !== -1;
  }
  get isFinalStage(): boolean {
    return this.stageIndex === LIFECYCLE_STAGES.length - 1;
  }
  get nextStageLabel(): string | null {
    if (!this.isOnStandardSequence || this.isFinalStage) return null;
    return LIFECYCLE_STAGES[this.stageIndex + 1].label;
  }
  get canAdvance(): boolean {
    return this.isOnStandardSequence && !this.isFinalStage && this.pendingOnly.length === 0;
  }
  get advanceBlockedReason(): string {
    if (!this.isOnStandardSequence) return `${WORKOUT_STAGE.label} is a branch, not a rung on the standard sequence -- it has no automatic "next stage".`;
    if (this.isFinalStage) return 'This deal is already at the final stage.';
    if (this.pendingOnly.length) return `${this.pendingOnly.length} pending approval(s) at this stage must be resolved first.`;
    return '';
  }

  advanceStage(): void {
    if (!this.canAdvance) return;
    this.advancing.set(true);
    this.api.advanceStage(this.dealId, this.session.name()).subscribe({
      next: (res) => {
        this.advancing.set(false);
        this.snack.open(`Advanced to "${res.to_stage_label}".`, 'Dismiss', { duration: 4000 });
        this.load();
      },
      error: (err) => {
        this.advancing.set(false);
        this.snack.open(err?.error?.detail ?? 'Could not advance this deal to the next stage.', 'Dismiss', { duration: 5000 });
      },
    });
  }
}
