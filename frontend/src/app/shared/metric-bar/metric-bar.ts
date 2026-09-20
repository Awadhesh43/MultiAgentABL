import { Component, computed, input } from '@angular/core';
import { MatTooltipModule } from '@angular/material/tooltip';

/** A 0..1 score as a small bar plus a percentage, or a dash when it doesn't apply. */
@Component({
  selector: 'app-metric-bar',
  imports: [MatTooltipModule],
  template: `
    @if (value() === null) {
      <span class="na" [matTooltip]="naHint()">&mdash;</span>
    } @else {
      <span class="mb" [matTooltip]="hint()">
        <span class="track"><span class="fill" [class]="tone()" [style.width.%]="pct()"></span></span>
        <span class="num">{{ pct() }}%</span>
      </span>
    }
  `,
  styles: [
    `
      :host { display: inline-block; }
      .mb { display: inline-flex; align-items: center; gap: 0.45rem; }
      .track { width: 46px; height: 6px; border-radius: 999px; background: var(--status-pending-bg); overflow: hidden; }
      .fill { display: block; height: 100%; border-radius: 999px; }
      .good { background: var(--guardrail-pass); }
      .mid { background: #d4a017; }
      .low { background: var(--guardrail-blocked); }
      .num { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; font-variant-numeric: tabular-nums; min-width: 2.6ch; }
      .na { color: var(--mat-sys-on-surface-variant, #8a949d); }
    `,
  ],
})
export class MetricBar {
  value = input<number | null>(null);
  hint = input('');
  naHint = input('Does not apply to this kind of call');

  protected pct = computed(() => Math.round((this.value() ?? 0) * 100));
  protected tone = computed(() => {
    const v = this.value() ?? 0;
    return v >= 0.8 ? 'fill good' : v >= 0.5 ? 'fill mid' : 'fill low';
  });
}
