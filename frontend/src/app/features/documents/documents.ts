import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe, PercentPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';
import { Api } from '../../core/api';
import { Session } from '../../core/session';
import { DEAL_FIELD_OPTIONS, DealSummary, DocumentRecord, DocumentType, ExtractedField } from '../../core/models';
import { StatusBadge } from '../../shared/status-badge/status-badge';

@Component({
  selector: 'app-documents',
  imports: [
    FormsModule, MatCardModule, MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatSelectModule, MatCheckboxModule, MatExpansionModule, MatProgressSpinnerModule, DatePipe, PercentPipe, StatusBadge,
  ],
  templateUrl: './documents.html',
  styleUrl: './documents.scss',
})
export class Documents implements OnInit {
  private api = inject(Api);
  private snack = inject(MatSnackBar);
  protected session = inject(Session);

  protected readonly dealFieldOptions = DEAL_FIELD_OPTIONS;
  protected loading = signal(true);
  protected documentTypes = signal<DocumentType[]>([]);
  protected deals = signal<DealSummary[]>([]);
  protected documents = signal<DocumentRecord[]>([]);
  protected selectedDocument = signal<DocumentRecord | null>(null);
  protected fieldValues = signal<Record<string, string>>({});
  protected fieldMapping = signal<Record<string, string>>({});

  // upload form state
  protected uploadTypeId = signal<string>('');
  protected uploadDealId = signal<string>('');
  protected uploadFile = signal<File | null>(null);
  protected uploading = signal(false);

  // new key term form state, per document type id
  protected newTermLabel = signal<Record<string, string>>({});
  protected newTermAliases = signal<Record<string, string>>({});
  protected newTermType = signal<Record<string, string>>({});

  // edit-existing-term state: only one term editable at a time, and only its aliases
  protected editingTermId = signal<string | null>(null);
  protected editAliasesInput = signal<Record<string, string>>({});

  ngOnInit(): void {
    this.loadAll();
  }

  loadAll(): void {
    this.loading.set(true);
    forkJoin({
      types: this.api.listDocumentTypes(),
      deals: this.api.listDeals(),
      documents: this.api.listDocuments(),
    }).subscribe(({ types, deals, documents }) => {
      this.documentTypes.set(types);
      this.deals.set(deals);
      this.documents.set(documents.sort((a, b) => (a.uploaded_at < b.uploaded_at ? 1 : -1)));
      if (!this.uploadTypeId() && types.length) this.uploadTypeId.set(types[0].id);
      this.loading.set(false);
    });
  }

  // --- key terms ---

  termDataType(typeId: string): string {
    return this.newTermType()[typeId] ?? 'text';
  }
  setTermDataType(typeId: string, value: string): void {
    this.newTermType.update((m) => ({ ...m, [typeId]: value }));
  }
  termLabel(typeId: string): string {
    return this.newTermLabel()[typeId] ?? '';
  }
  setTermLabel(typeId: string, value: string): void {
    this.newTermLabel.update((m) => ({ ...m, [typeId]: value }));
  }
  termAliases(typeId: string): string {
    return this.newTermAliases()[typeId] ?? '';
  }
  setTermAliases(typeId: string, value: string): void {
    this.newTermAliases.update((m) => ({ ...m, [typeId]: value }));
  }

  addKeyTerm(typeId: string): void {
    const label = this.termLabel(typeId).trim();
    if (!label) return;
    const aliases = this.termAliases(typeId).split(',').map((s) => s.trim()).filter(Boolean);
    const dataType = this.termDataType(typeId) || 'text';
    this.api.addKeyTerm(typeId, { label, aliases, data_type: dataType, required: true }).subscribe(() => {
      this.setTermLabel(typeId, '');
      this.setTermAliases(typeId, '');
      this.snack.open(`Added "${label}" to the key term list.`, 'Dismiss', { duration: 3000 });
      this.loadAll();
    });
  }

  removeKeyTerm(typeId: string, termId: string): void {
    this.api.removeKeyTerm(typeId, termId).subscribe(() => this.loadAll());
  }

  isEditingTerm(termId: string): boolean {
    return this.editingTermId() === termId;
  }

  startEditTerm(termId: string): void {
    this.editingTermId.set(termId);
    this.editAliasesInput.update((m) => ({ ...m, [termId]: '' }));
  }

  cancelEditTerm(): void {
    this.editingTermId.set(null);
  }

  editAliasesValue(termId: string): string {
    return this.editAliasesInput()[termId] ?? '';
  }
  setEditAliasesValue(termId: string, value: string): void {
    this.editAliasesInput.update((m) => ({ ...m, [termId]: value }));
  }

  saveTermAliases(typeId: string, termId: string): void {
    const aliasesToAdd = this.editAliasesValue(termId).split(',').map((s) => s.trim()).filter(Boolean);
    if (!aliasesToAdd.length) {
      this.snack.open('Enter at least one alias to add.', 'Dismiss', { duration: 3000 });
      return;
    }
    this.api.addKeyTermAliases(typeId, termId, aliasesToAdd).subscribe({
      next: () => {
        this.snack.open(`Added ${aliasesToAdd.length} alias(es).`, 'Dismiss', { duration: 3000 });
        this.editingTermId.set(null);
        this.loadAll();
      },
      error: (err) => {
        this.snack.open(err?.error?.detail ?? 'Could not add those aliases.', 'Dismiss', { duration: 4000 });
      },
    });
  }

  // --- upload ---

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.uploadFile.set(input.files?.[0] ?? null);
  }

  upload(): void {
    const file = this.uploadFile();
    if (!file || !this.uploadTypeId()) return;
    this.uploading.set(true);
    this.api.uploadDocument(file, this.uploadTypeId(), this.uploadDealId() || null, this.session.name()).subscribe({
      next: (doc) => {
        this.uploading.set(false);
        this.uploadFile.set(null);
        this.openDocument(doc);
        this.loadAll();
      },
      error: () => this.uploading.set(false),
    });
  }

  // --- review ---

  openDocument(doc: DocumentRecord): void {
    this.selectedDocument.set(doc);
    const values: Record<string, string> = {};
    for (const f of doc.extracted_fields) values[f.id] = f.extracted_value;
    this.fieldValues.set(values);
    this.fieldMapping.set({});
  }

  fieldValue(fieldId: string): string {
    return this.fieldValues()[fieldId] ?? '';
  }
  setFieldValue(fieldId: string, value: string): void {
    this.fieldValues.update((m) => ({ ...m, [fieldId]: value }));
  }

  confidenceClass(confidence: number): string {
    if (confidence >= 0.75) return 'badge-approved';
    if (confidence >= 0.5) return 'badge-pending';
    return 'badge-rejected';
  }

  reviewField(field: ExtractedField, confirm: boolean): void {
    const doc = this.selectedDocument();
    if (!doc) return;
    this.api.reviewField(doc.id, field.id, this.fieldValue(field.id), this.session.name(), confirm).subscribe(() => {
      this.refreshSelectedDocument(doc.id);
    });
  }

  private refreshSelectedDocument(docId: string): void {
    this.api.listDocuments().subscribe((docs) => {
      this.documents.set(docs.sort((a, b) => (a.uploaded_at < b.uploaded_at ? 1 : -1)));
      const updated = docs.find((d) => d.id === docId) ?? null;
      if (updated) this.openDocument(updated);
    });
  }

  mappingFor(fieldId: string): string {
    return this.fieldMapping()[fieldId] ?? '';
  }
  setMapping(fieldId: string, value: string): void {
    this.fieldMapping.update((m) => ({ ...m, [fieldId]: value }));
  }

  applyToDeal(): void {
    const doc = this.selectedDocument();
    if (!doc || !doc.deal_id) return;
    const mapping = this.fieldMapping();
    const fieldIds = Object.keys(mapping).filter((id) => mapping[id]);
    if (!fieldIds.length) {
      this.snack.open('Map at least one confirmed field to a deal attribute first.', 'Dismiss', { duration: 3000 });
      return;
    }
    this.api.applyToDeal(doc.id, fieldIds, mapping, this.session.name()).subscribe((res) => {
      const parts: string[] = [];
      if (res.created.length) parts.push(`staged ${res.created.length} change(s) in the approvals queue`);
      if (res.skipped.length) {
        const detail = res.skipped.map((s) => `${s.label} (${s.reason})`).join('; ');
        parts.push(`skipped ${res.skipped.length} field(s) that were empty or didn't match the expected format: ${detail}`);
      }
      this.snack.open(parts.join(' -- ') || 'Nothing to stage.', 'Dismiss', { duration: 6000 });
      this.fieldMapping.set({});
    });
  }

  dealName(id: string | null): string {
    if (!id) return 'Unassigned';
    return this.deals().find((d) => d.id === id)?.borrower_name ?? id;
  }

  typeName(id: string): string {
    return this.documentTypes().find((t) => t.id === id)?.name ?? id;
  }
}
