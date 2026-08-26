import { Component, OnInit, inject, signal } from '@angular/core';
import { CurrencyPipe } from '@angular/common';
import { Router } from '@angular/router';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { DealSummary } from '../../core/models';

@Component({
  selector: 'app-dashboard',
  imports: [MatTableModule, MatChipsModule, MatIconModule, MatTooltipModule, MatProgressSpinnerModule, CurrencyPipe],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.scss',
})
export class Dashboard implements OnInit {
  private api = inject(Api);
  private router = inject(Router);

  protected loading = signal(true);
  protected deals = signal<DealSummary[]>([]);
  protected pendingByDeal = signal<Map<string, number>>(new Map());

  readonly columns = ['borrower', 'stage', 'risk_rating', 'availability', 'outstanding', 'pending'];

  ngOnInit(): void {
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

  open(deal: DealSummary): void {
    this.router.navigate(['/deals', deal.id]);
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
