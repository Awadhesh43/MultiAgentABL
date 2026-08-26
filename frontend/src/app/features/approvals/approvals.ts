import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { DealSummary, GuardrailStatus, PendingChange } from '../../core/models';
import { GuardrailBadge } from '../../shared/guardrail-badge/guardrail-badge';
import { StatusBadge } from '../../shared/status-badge/status-badge';
import { DecisionDialog, DecisionDialogData } from '../../shared/decision-dialog/decision-dialog';

type StatusFilter = 'pending' | 'approved' | 'rejected' | 'all';

@Component({
  selector: 'app-approvals',
  imports: [RouterLink, FormsModule, MatCardModule, MatButtonModule, MatButtonToggleModule, MatProgressSpinnerModule, DatePipe, GuardrailBadge, StatusBadge],
  templateUrl: './approvals.html',
  styleUrl: './approvals.scss',
})
export class Approvals implements OnInit {
  private api = inject(Api);
  private dialog = inject(MatDialog);

  protected loading = signal(true);
  protected changes = signal<PendingChange[]>([]);
  protected dealNames = signal<Map<string, string>>(new Map());
  protected roles = signal<string[]>([]);
  protected statusFilter = signal<StatusFilter>('pending');
  protected guardrailFilter = signal<GuardrailStatus | 'all'>('all');

  protected filtered = computed(() => {
    let list = this.changes();
    if (this.statusFilter() !== 'all') list = list.filter((c) => c.status === this.statusFilter());
    if (this.guardrailFilter() !== 'all') list = list.filter((c) => c.guardrail_status === this.guardrailFilter());
    return list;
  });

  ngOnInit(): void {
    this.load();
    this.api.listRoles().subscribe((r) => this.roles.set(r));
  }

  load(): void {
    this.loading.set(true);
    forkJoin({ changes: this.api.listPendingChanges(), deals: this.api.listDeals() }).subscribe(({ changes, deals }) => {
      const names = new Map<string, string>();
      for (const d of deals as DealSummary[]) names.set(d.id, d.borrower_name);
      this.changes.set(changes.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)));
      this.dealNames.set(names);
      this.loading.set(false);
    });
  }

  dealName(id: string): string {
    return this.dealNames().get(id) ?? id;
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
}
