import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { Router } from '@angular/router';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSortModule, Sort } from '@angular/material/sort';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { Session } from '../../core/session';
import { DealCreate, DealSummary, LIFECYCLE_STAGES, WORKOUT_STAGE } from '../../core/models';
import { BorrowerOption, CreateDealDialog, CreateDealDialogData } from '../../shared/create-deal-dialog/create-deal-dialog';

// Ordered worst-to-best isn't how a credit reviewer scans a portfolio -- best
// (Pass) to worst (Loss) is -- so risk rating sorts by position in this list,
// not alphabetically. Mirrors guardrails.RATING_ORDER on the backend.
const RATING_ORDER = ['Pass', 'Special Mention', 'Substandard', 'Doubtful', 'Loss'];

// Stage sorts by position in the lifecycle, not alphabetically, so ascending
// reads as "earliest in the deal's life" to "latest." The workout branch
// isn't a rung on that ladder -- it sorts after every standard stage.
const STAGE_ORDER = [...LIFECYCLE_STAGES.map((s) => s.id), WORKOUT_STAGE.id];

type SortableColumn = 'borrower' | 'created' | 'stage' | 'risk_rating' | 'availability' | 'outstanding' | 'pending';

@Component({
  selector: 'app-dashboard',
  imports: [
    MatTableModule, MatChipsModule, MatIconModule, MatButtonModule, MatTooltipModule,
    MatProgressSpinnerModule, MatSortModule, CurrencyPipe, DatePipe,
  ],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard implements OnInit {
  private api = inject(Api);
  private router = inject(Router);
  private dialog = inject(MatDialog);
  private snack = inject(MatSnackBar);
  private session = inject(Session);

  protected loading = signal(true);
  protected deals = signal<DealSummary[]>([]);
  protected pendingByDeal = signal<Map<string, number>>(new Map());
  // Newest deals first by default -- the same "what just happened" framing
  // as the recency-based defaults elsewhere in the app (recent documents,
  // recent audit entries).
  protected sortState = signal<Sort>({ active: 'created', direction: 'desc' });

  readonly columns = ['borrower', 'created', 'stage', 'risk_rating', 'availability', 'outstanding', 'pending'];

  protected sortedDeals = computed<DealSummary[]>(() => {
    const { active, direction } = this.sortState();
    const rows = this.deals();
    if (!active || !direction) return rows;

    const factor = direction === 'asc' ? 1 : -1;
    const key = active as SortableColumn;
    return [...rows].sort((a, b) => factor * this.compare(a, b, key));
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    forkJoin({ deals: this.api.listDeals(), pending: this.api.listPendingChanges('pending') }).subscribe(
      ({ deals, pending }) => {
        const counts = new Map<string, number>();
        for (const c of pending) counts.set(c.deal_id, (counts.get(c.deal_id) ?? 0) + 1);
        this.deals.set(deals);
        this.pendingByDeal.set(counts);
        this.loading.set(false);
      },
    );
  }

  onSortChange(sort: Sort): void {
    this.sortState.set(sort);
  }

  private compare(a: DealSummary, b: DealSummary, column: SortableColumn): number {
    switch (column) {
      case 'borrower':
        return a.borrower_name.localeCompare(b.borrower_name);
      case 'created':
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      case 'stage':
        return this.stageRank(a.stage) - this.stageRank(b.stage);
      case 'risk_rating':
        return this.ratingRank(a.risk_rating) - this.ratingRank(b.risk_rating);
      case 'availability':
        return a.latest_availability - b.latest_availability;
      case 'outstanding':
        return a.outstanding_balance - b.outstanding_balance;
      case 'pending':
        return this.pendingCount(a.id) - this.pendingCount(b.id);
    }
  }

  private stageRank(stage: string): number {
    const idx = STAGE_ORDER.indexOf(stage);
    return idx === -1 ? STAGE_ORDER.length : idx;
  }

  private ratingRank(rating: string): number {
    const idx = RATING_ORDER.indexOf(rating);
    return idx === -1 ? RATING_ORDER.length : idx;
  }

  open(deal: DealSummary): void {
    this.router.navigate(['/deals', deal.id]);
  }

  createDeal(): void {
    const data: CreateDealDialogData = { existingBorrowers: this.uniqueBorrowers() };
    this.dialog
      .open(CreateDealDialog, { width: '480px', data })
      .afterClosed()
      .subscribe((draft: Omit<DealCreate, 'created_by'> | undefined) => {
        if (!draft) return;
        const deal: DealCreate = { ...draft, created_by: this.session.name() };
        this.api.createDeal(deal).subscribe({
          next: (created) => {
            this.snack.open(`Created "${created.deal_name}" at Origination.`, 'Dismiss', { duration: 4000 });
            this.router.navigate(['/deals', created.id]);
          },
          error: (err) => {
            this.snack.open(err?.error?.detail ?? 'Could not create this deal.', 'Dismiss', { duration: 5000 });
          },
        });
      });
  }

  private uniqueBorrowers(): BorrowerOption[] {
    const seen = new Map<string, BorrowerOption>();
    for (const d of this.deals()) {
      const key = d.borrower_name.trim().toLowerCase();
      if (!seen.has(key)) seen.set(key, { name: d.borrower_name, industry: d.industry });
    }
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }

  pendingCount(dealId: string): number {
    return this.pendingByDeal().get(dealId) ?? 0;
  }

  ratingClass(rating: string): string {
    if (rating === 'Pass') return 'rating-pass';
    if (rating === 'Special Mention') return 'rating-watch';
    return 'rating-classified';
  }

  stageLabel(stage: string): string {
    return stage
      .split('_')
      .map((w) => w[0].toUpperCase() + w.slice(1))
      .join(' ');
  }
}
