import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Api } from '../../core/api';

interface ChatMessage {
  role: 'user' | 'agent';
  text: string;
  citations?: { source: string; title: string }[];
  grounded?: boolean;
}

const STARTERS = [
  'What is a borrowing base and how is it calculated?',
  'What triggers springing cash dominion?',
  'How does dilution affect availability?',
  'What is a FILO tranche?',
  'When does a field exam get accelerated?',
];

@Component({
  selector: 'app-wiki',
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  templateUrl: './wiki.html',
  styleUrl: './wiki.scss',
})
export class Wiki {
  private api = inject(Api);
  @ViewChild('scrollAnchor') private scrollAnchor?: ElementRef<HTMLDivElement>;

  protected readonly starters = STARTERS;
  protected messages = signal<ChatMessage[]>([
    {
      role: 'agent',
      text: "I'm the ABL Wiki agent. Ask me about ABL terms, borrowing base mechanics, covenants, the lifecycle, field exams, or governance -- I only answer from the bank's curated knowledge base and cite what I use.",
    },
  ]);
  protected question = signal('');
  protected asking = signal(false);

  ask(text?: string): void {
    const q = (text ?? this.question()).trim();
    if (!q || this.asking()) return;
    this.messages.update((m) => [...m, { role: 'user', text: q }]);
    this.question.set('');
    this.asking.set(true);
    this.scrollSoon();

    this.api.askWiki(q).subscribe({
      next: (res) => {
        this.messages.update((m) => [...m, { role: 'agent', text: res.answer, citations: res.citations, grounded: res.grounded }]);
        this.asking.set(false);
        this.scrollSoon();
      },
      error: () => {
        this.messages.update((m) => [...m, { role: 'agent', text: 'Something went wrong reaching the wiki service.' }]);
        this.asking.set(false);
      },
    });
  }

  private scrollSoon(): void {
    setTimeout(() => this.scrollAnchor?.nativeElement.scrollIntoView({ behavior: 'smooth' }), 50);
  }

  citationLabel(msg: ChatMessage): string {
    return (msg.citations ?? []).map((c) => `${c.title} (${c.source})`).join('; ');
  }
}
