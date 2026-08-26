import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatBadgeModule } from '@angular/material/badge';
import { MatMenuModule } from '@angular/material/menu';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { FormsModule } from '@angular/forms';
import { Api } from './core/api';
import { Session } from './core/session';

@Component({
  imports: [
    RouterOutlet, RouterLink, RouterLinkActive, MatToolbarModule, MatButtonModule, MatIconModule,
    MatBadgeModule, MatMenuModule, MatFormFieldModule, MatSelectModule, MatInputModule, FormsModule,
  ],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private api = inject(Api);
  protected session = inject(Session);

  protected readonly pendingCount = signal(0);
  protected readonly roles = signal<string[]>([]);

  ngOnInit(): void {
    this.refreshPendingCount();
    this.api.listRoles().subscribe((roles) => this.roles.set(roles));
  }

  refreshPendingCount(): void {
    this.api.listPendingChanges('pending').subscribe((changes) => this.pendingCount.set(changes.length));
  }
}
