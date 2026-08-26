import { Component, computed, input } from '@angular/core';
import { GuardrailStatus } from '../../core/models';

const LABELS: Record<GuardrailStatus, string> = {
  pass: 'Pass',
  warn: 'Warn',
  requires_elevated_approval: 'Elevated approval required',
  blocked: 'Blocked',
};

const CLASSES: Record<GuardrailStatus, string> = {
  pass: 'badge badge-pass',
  warn: 'badge badge-warn',
  requires_elevated_approval: 'badge badge-elevated',
  blocked: 'badge badge-blocked',
};

@Component({
  selector: 'app-guardrail-badge',
  template: `<span [class]="cssClass()">{{ label() }}</span>`,
})
export class GuardrailBadge {
  status = input.required<GuardrailStatus>();
  protected label = computed(() => LABELS[this.status()]);
  protected cssClass = computed(() => CLASSES[this.status()]);
}
