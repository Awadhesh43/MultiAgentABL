import { Component, computed, input } from '@angular/core';
import { ChangeStatus } from '../../core/models';

const LABELS: Record<ChangeStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

const CLASSES: Record<ChangeStatus, string> = {
  pending: 'badge badge-pending',
  approved: 'badge badge-approved',
  rejected: 'badge badge-rejected',
};

@Component({
  selector: 'app-status-badge',
  template: `<span [class]="cssClass()">{{ label() }}</span>`,
})
export class StatusBadge {
  status = input.required<ChangeStatus>();
  protected label = computed(() => LABELS[this.status()]);
  protected cssClass = computed(() => CLASSES[this.status()]);
}
