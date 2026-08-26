import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { AuditEntry, ChainStatus, DealSummary } from '../../core/models';

@Component({
  selector: 'app-audit',
  imports: [RouterLink, FormsModule, MatFormFieldModule, MatInputModule, MatIconModule, MatProgressSpinnerModule, MatTooltipModule, DatePipe],
  templateUrl: './audit.html',
  styleUrl: './audit.scss',
})
export class Audit implements OnInit {
  private api = inject(Api);

  protected loading = signal(true);
  protected entries = signal<AuditEntry[]>([]);
  protected chain = signal<ChainStatus | null>(null);
  protected dealNames = signal<Map<string, string>>(new Map());
  protected search = signal('');

  protected filtered = computed(() => {
    const q = this.search().toLowerCase().trim();
    if (!q) return this.entries();
    return this.entries().filter(
      (e) =>
        e.summary.toLowerCase().includes(q) ||
        e.actor.toLowerCase().includes(q) ||
        e.event_type.toLowerCase().includes(q) ||
        this.dealName(e.deal_id).toLowerCase().includes(q),
    );
  });

  ngOnInit(): void {
    forkJoin({ entries: this.api.listAudit(), chain: this.api.verifyChain(), deals: this.api.listDeals() }).subscribe(
      ({ entries, chain, deals }) => {
        const names = new Map<string, string>();
        for (const d of deals as DealSummary[]) names.set(d.id, d.borrower_name);
        this.entries.set(entries);
        this.chain.set(chain);
        this.dealNames.set(names);
        this.loading.set(false);
      },
    );
  }

  dealName(id: string): string {
    if (!id) return '';
    return this.dealNames().get(id) ?? id;
  }

  eventClass(eventType: string): string {
    if (eventType.includes('rejection')) return 'evt-reject';
    if (eventType.includes('approval')) return 'evt-approve';
    if (eventType.includes('blocked') || eventType.includes('breach')) return 'evt-flag';
    return 'evt-default';
  }
}
