import { Component, OnInit, WritableSignal, computed, inject, signal } from '@angular/core';
import { DatePipe, PercentPipe } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Api } from '../../core/api';
import { Session } from '../../core/session';
import { DocumentReference, Evidence, ReferenceField, ReferenceSection } from '../../core/models';
import { StatusBadge } from '../../shared/status-badge/status-badge';

const SECTION_SEP = ' › ';
const NO_SECTION = '';

const OUTCOME_LABELS: Record<Evidence['outcome'], string> = {
  selected: 'Used: the value was read from this passage',
  selected_untyped: 'Used: only untyped text was found here (low confidence)',
  selected_fallback: 'Used: found by searching the whole document',
  no_value_in_chunk: 'Skipped: no value next to the label',
  type_mismatch: 'Skipped: the value did not match the expected type',
  not_examined: 'Not examined: a better match had already been found',
};

interface TextPart {
  text: string;
  hit: boolean;
}

@Component({
  selector: 'app-document-reference',
  imports: [
    RouterLink, FormsModule, MatCardModule, MatButtonModule, MatIconModule, MatFormFieldModule, MatInputModule,
    MatProgressSpinnerModule, MatTooltipModule, DatePipe, PercentPipe, StatusBadge,
  ],
  templateUrl: './document-reference.html',
  styleUrl: './document-reference.scss',
})
export class DocumentReferenceView implements OnInit {
  private route = inject(ActivatedRoute);
  private api = inject(Api);
  protected session = inject(Session);

  protected readonly noSection = NO_SECTION;
  protected loading = signal(true);
  protected error = signal('');
  protected reference = signal<DocumentReference | null>(null);
  protected selectedFieldId = signal<string | null>(null);
  protected sectionFilter = signal<string | null>(null);

  protected editValues = signal<Record<string, string>>({});
  protected saving = signal(false);
  /** evidence ids currently showing the whole page instead of the cropped passage */
  protected wholePage = signal<ReadonlySet<string>>(new Set());
  /** evidence ids of the "other passages" whose screenshot is open */
  protected openOthers = signal<ReadonlySet<string>>(new Set());
  protected brokenImages = signal<ReadonlySet<string>>(new Set());

  protected visibleFields = computed(() => {
    const ref = this.reference();
    if (!ref) return [];
    const filter = this.sectionFilter();
    if (filter === null) return ref.fields;
    return ref.fields.filter((f) => this.sourceOf(f)?.section === filter);
  });

  protected selected = computed(() => {
    const ref = this.reference();
    if (!ref) return null;
    return ref.fields.find((f) => f.field_id === this.selectedFieldId()) ?? null;
  });

  protected reviewedCount = computed(() => this.reference()?.fields.filter((f) => f.status !== 'pending_review').length ?? 0);

  ngOnInit(): void {
    this.load(true);
  }

  private load(selectFirst: boolean): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.api.getDocumentReference(id).subscribe({
      next: (ref) => {
        this.reference.set(ref);
        this.editValues.set({});
        this.loading.set(false);
        const keep = ref.fields.some((f) => f.field_id === this.selectedFieldId());
        if (selectFirst || !keep) {
          const first = ref.fields.find((f) => this.sourceOf(f)) ?? ref.fields[0];
          this.selectedFieldId.set(first?.field_id ?? null);
        }
      },
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'Could not load this document.');
        this.loading.set(false);
      },
    });
  }

  // --- helpers used by the template ---

  sourceOf(field: ReferenceField): Evidence | undefined {
    return field.evidence.find((e) => e.used);
  }

  otherEvidence(field: ReferenceField): Evidence[] {
    return field.evidence.filter((e) => !e.used);
  }

  outcomeLabel(ev: Evidence): string {
    return OUTCOME_LABELS[ev.outcome];
  }

  pageLabel(ev: Evidence | undefined): string {
    if (!ev) return '';
    if (ev.page === null) return 'No page numbers';
    return ev.page_source === 'docx_markers' ? `Page ~${ev.page}` : `Page ${ev.page}`;
  }

  sectionLabel(section: string): string {
    return section || 'Before the first heading';
  }

  sectionParts(section: string): string[] {
    return section ? section.split(SECTION_SEP) : [];
  }

  pageRange(section: ReferenceSection, approximate: boolean): string {
    if (section.page_start === null) return '';
    const tilde = approximate ? '~' : '';
    return section.page_start === section.page_end
      ? `p. ${tilde}${section.page_start}`
      : `p. ${tilde}${section.page_start}-${section.page_end}`;
  }

  confidenceClass(confidence: number): string {
    if (confidence >= 0.75) return 'badge-approved';
    if (confidence >= 0.5) return 'badge-pending';
    return 'badge-rejected';
  }

  /** Splits a chunk's text around the raw value so the value can be highlighted. */
  textParts(text: string, value: string): TextPart[] {
    const needle = value.trim();
    const at = needle ? text.indexOf(needle) : -1;
    if (at < 0) return [{ text, hit: false }];
    return [
      { text: text.slice(0, at), hit: false },
      { text: needle, hit: true },
      { text: text.slice(at + needle.length), hit: false },
    ];
  }

  imageSrc(ev: Evidence): string {
    return this.wholePage().has(ev.evidence_id) ? ev.page_image_url : ev.image_url;
  }

  isWholePage(ev: Evidence): boolean {
    return this.wholePage().has(ev.evidence_id);
  }

  toggleWholePage(ev: Evidence): void {
    this.toggleIn(this.wholePage, ev.evidence_id);
  }

  isOpen(ev: Evidence): boolean {
    return this.openOthers().has(ev.evidence_id);
  }

  toggleOther(ev: Evidence): void {
    this.toggleIn(this.openOthers, ev.evidence_id);
  }

  private toggleIn(target: WritableSignal<ReadonlySet<string>>, id: string): void {
    const next = new Set(target());
    if (!next.delete(id)) next.add(id);
    target.set(next);
  }

  markBroken(ev: Evidence): void {
    this.brokenImages.update((s) => new Set(s).add(ev.evidence_id));
  }

  isBroken(ev: Evidence): boolean {
    return this.brokenImages().has(ev.evidence_id);
  }

  fileUrl(): string {
    const ref = this.reference();
    if (!ref) return '';
    const url = this.api.documentFileUrl(ref.document.id);
    const selected = this.selected();
    const page = selected ? this.sourceOf(selected)?.page : null;
    // Browsers' built-in PDF viewer honours #page=N; other formats just download/open.
    return ref.document.file_kind === 'pdf' && page ? `${url}#page=${page}` : url;
  }

  // --- interaction ---

  selectField(field: ReferenceField): void {
    this.selectedFieldId.set(field.field_id);
  }

  toggleSection(section: string): void {
    this.sectionFilter.update((current) => (current === section ? null : section));
  }

  valueFor(field: ReferenceField): string {
    return this.editValues()[field.field_id] ?? field.value;
  }

  setValue(field: ReferenceField, value: string): void {
    this.editValues.update((m) => ({ ...m, [field.field_id]: value }));
  }

  review(field: ReferenceField, confirm: boolean): void {
    const ref = this.reference();
    if (!ref) return;
    this.saving.set(true);
    this.api.reviewField(ref.document.id, field.field_id, this.valueFor(field), this.session.name(), confirm).subscribe({
      next: () => {
        this.saving.set(false);
        this.load(false);
      },
      error: () => this.saving.set(false),
    });
  }
}
