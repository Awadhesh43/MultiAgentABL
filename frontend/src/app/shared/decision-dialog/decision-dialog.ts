import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { ApprovalDecision, PendingChange } from '../../core/models';
import { Session } from '../../core/session';
import { GuardrailBadge } from '../guardrail-badge/guardrail-badge';

export interface DecisionDialogData {
  change: PendingChange;
  roles: string[];
}

@Component({
  selector: 'app-decision-dialog',
  imports: [
    FormsModule, MatDialogModule, MatButtonModule, MatButtonToggleModule, MatFormFieldModule,
    MatInputModule, MatSelectModule, MatCheckboxModule, MatIconModule, GuardrailBadge,
  ],
  templateUrl: './decision-dialog.html',
  styleUrl: './decision-dialog.scss',
})
export class DecisionDialog {
  private ref = inject(MatDialogRef<DecisionDialog>);
  private session = inject(Session);
  protected data = inject<DecisionDialogData>(MAT_DIALOG_DATA);

  protected approve = signal(true);
  protected decidedBy = signal(this.session.name());
  protected role = signal(this.session.role());
  protected notes = signal('');
  protected override = signal(false);

  protected get isBlocked(): boolean {
    return this.data.change.guardrail_status === 'blocked';
  }
  protected get isElevated(): boolean {
    return this.data.change.guardrail_status === 'requires_elevated_approval';
  }
  protected get requiredAuthority(): string {
    return this.data.change.required_authority;
  }

  protected get canSubmit(): boolean {
    if (!this.approve()) return true;
    if (this.isBlocked) return this.override() && this.notes().trim().length > 0;
    return true;
  }

  submit(): void {
    if (!this.canSubmit) return;
    const decision: ApprovalDecision = {
      approve: this.approve(),
      decided_by: this.decidedBy() || 'Anonymous reviewer',
      role: this.role(),
      notes: this.notes(),
      override: this.approve() && this.isBlocked ? this.override() : false,
    };
    this.ref.close(decision);
  }

  cancel(): void {
    this.ref.close(undefined);
  }
}
