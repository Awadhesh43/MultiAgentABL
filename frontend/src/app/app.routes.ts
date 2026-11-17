import { Routes } from '@angular/router';
import { Dashboard } from './features/dashboard/dashboard';
import { DealDetail } from './features/deal-detail/deal-detail';
import { Approvals } from './features/approvals/approvals';
import { Documents } from './features/documents/documents';
import { Audit } from './features/audit/audit';
import { Wiki } from './features/wiki/wiki';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', component: Dashboard, title: 'Portfolio - Agentic ABL' },
  { path: 'deals/:id', component: DealDetail, title: 'Deal - Agentic ABL' },
  { path: 'approvals', component: Approvals, title: 'Approvals - Agentic ABL' },
  { path: 'documents', component: Documents, title: 'Document Intake - Agentic ABL' },
  { path: 'audit', component: Audit, title: 'Audit Trail - Agentic ABL' },
  { path: 'wiki', component: Wiki, title: 'ABL Wiki - Agentic ABL' },
  { path: '**', redirectTo: 'dashboard' },
];
