import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { DealCreate } from '../../core/models';

export interface BorrowerOption {
  name: string;
  industry: string;
}

export interface CreateDealDialogData {
  existingBorrowers: BorrowerOption[];
}

const MAX_SUGGESTIONS = 8;

@Component({
  selector: 'app-create-deal-dialog',
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatAutocompleteModule],
  templateUrl: './create-deal-dialog.html',
  styleUrl: './create-deal-dialog.scss',
})
export class CreateDealDialog {
  private ref = inject(MatDialogRef<CreateDealDialog>);
  protected data = inject<CreateDealDialogData>(MAT_DIALOG_DATA);

  protected borrowerName = signal('');
  protected dealName = signal('');
  protected industry = signal('');
  protected commitment = signal<number | null>(null);
  protected submitted = signal(false);
  protected matchedExistingBorrower = signal(false);

  protected borrowerNameError = computed(() => this.submitted() && !this.borrowerName().trim());
  protected dealNameError = computed(() => this.submitted() && !this.dealName().trim());
  protected commitmentError = computed(() => this.submitted() && !(this.commitment()! > 0));

  protected filteredBorrowers = computed<BorrowerOption[]>(() => {
    const query = this.borrowerName().trim().toLowerCase();
    const all = this.data.existingBorrowers;
    const pool = query ? all.filter((b) => b.name.toLowerCase().includes(query)) : all;
    return pool.slice(0, MAX_SUGGESTIONS);
  });

  private findExisting(name: string): BorrowerOption | undefined {
    const query = name.trim().toLowerCase();
    return this.data.existingBorrowers.find((b) => b.name.toLowerCase() === query);
  }

  onBorrowerNameChange(value: string): void {
    this.borrowerName.set(value);
    this.matchedExistingBorrower.set(false);
  }

  onBorrowerOptionSelected(event: MatAutocompleteSelectedEvent): void {
    const match = this.findExisting(event.option.value);
    if (match) this.applyExistingBorrower(match);
  }

  onBorrowerNameBlur(): void {
    const match = this.findExisting(this.borrowerName());
    if (match) this.applyExistingBorrower(match);
  }

  private applyExistingBorrower(match: BorrowerOption): void {
    this.borrowerName.set(match.name);
    this.industry.set(match.industry);
    this.matchedExistingBorrower.set(true);
  }

  protected get dealNamePlaceholder(): string {
    const borrower = this.borrowerName().trim();
    return borrower ? `${borrower} ABL Facility` : 'e.g. "Cascade Machining -- $9.5mm ABL Revolver"';
  }

  submit(): void {
    this.submitted.set(true);
    if (this.borrowerNameError() || this.dealNameError() || this.commitmentError()) return;

    const deal: Omit<DealCreate, 'created_by'> = {
      borrower_name: this.borrowerName().trim(),
      deal_name: this.dealName().trim(),
      industry: this.industry().trim(),
      commitment: this.commitment()!,
    };
    this.ref.close(deal);
  }

  cancel(): void {
    this.ref.close(undefined);
  }
}
