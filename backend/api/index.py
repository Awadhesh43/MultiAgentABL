from pathlib import Path
import os
import shutil
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('/tmp/abl-platform') if os.environ.get('VERCEL') else ROOT
RUNTIME.mkdir(parents=True, exist_ok=True)
SOURCE_DB = ROOT / 'abl_platform.db'
DB = RUNTIME / 'abl_platform.db'
if SOURCE_DB.exists() and (not DB.exists() or DB.stat().st_size == 0):
    shutil.copyfile(SOURCE_DB, DB)

app = FastAPI(title='Agentic ABL Platform API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

def rows(table, where='', params=(), order=''):
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f'SELECT * FROM {table} {where} {order}', params).fetchall()]

def ensure_deal(deal_id: str):
    result = rows('deals', 'WHERE id = ?', (deal_id,))
    if not result:
        raise HTTPException(404, 'Deal not found')
    return result[0]

@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': DB.exists()}

@app.get('/api/dashboard')
def dashboard():
    deals = rows('deals', order='ORDER BY borrower_name')
    documents = rows('documents', order='ORDER BY uploaded_at DESC')
    return {'deals': deals, 'documents': documents, 'deal_count': len(deals), 'document_count': len(documents)}

@app.get('/api/deals')
def list_deals():
    return rows('deals', order='ORDER BY borrower_name')

@app.get('/api/deals/{deal_id}')
def get_deal(deal_id: str):
    return ensure_deal(deal_id)

@app.get('/api/deals/{deal_id}/stage-events')
def stage_events(deal_id: str):
    ensure_deal(deal_id)
    return rows('stage_events', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY entered_at ASC')

@app.get('/api/deals/{deal_id}/bbc')
def bbc(deal_id: str, limit: int = 10):
    ensure_deal(deal_id)
    safe_limit = max(1, min(limit, 100))
    return rows('borrowing_base_certificates', 'WHERE deal_id = ?', (deal_id,), f'ORDER BY created_at DESC LIMIT {safe_limit}')

@app.get('/api/deals/{deal_id}/pending-changes')
def deal_pending_changes(deal_id: str):
    ensure_deal(deal_id)
    return rows('pending_changes', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY created_at DESC')

@app.get('/api/pending-changes')
def pending_changes(status: str | None = None, deal_id: str | None = None):
    clauses, values = [], []
    if status: clauses.append('status = ?'); values.append(status)
    if deal_id: clauses.append('deal_id = ?'); values.append(deal_id)
    return rows('pending_changes', ('WHERE ' + ' AND '.join(clauses)) if clauses else '', tuple(values), 'ORDER BY created_at DESC')

@app.get('/api/pending-changes/roles')
def roles():
    return ['Credit Officer', 'Portfolio Manager', 'Operations Analyst', 'Relationship Manager']

@app.get('/api/documents')
def documents(deal_id: str | None = None):
    return rows('documents', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY uploaded_at DESC') if deal_id else rows('documents', order='ORDER BY uploaded_at DESC')

@app.get('/api/audit')
def audit(deal_id: str | None = None):
    return rows('audit_log', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY id DESC') if deal_id else rows('audit_log', order='ORDER BY id DESC')

__all__ = ['app']
