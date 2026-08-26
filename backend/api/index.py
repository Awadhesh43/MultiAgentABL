import os
import shutil
import sqlite3
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('/tmp/abl-platform') if os.environ.get('VERCEL') else ROOT
RUNTIME.mkdir(parents=True, exist_ok=True)
DB = RUNTIME / 'abl_platform.db'
BUNDLED_DB = ROOT / 'abl_platform.db'
if (not DB.exists() or DB.stat().st_size == 0) and BUNDLED_DB.exists():
    shutil.copyfile(BUNDLED_DB, DB)

app = FastAPI(title='Agentic ABL API')
origins = [x.strip() for x in os.environ.get('CORS_ORIGINS', '*').split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

def rows(table, order='', params=()):
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f'SELECT * FROM {table} {order}', params).fetchall()]

def ensure_deal(deal_id: str):
    if not rows('deals', 'WHERE id = ?', (deal_id,)):
        raise HTTPException(status_code=404, detail='Deal not found')

@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': DB.exists()}

@app.get('/api/deals')
def deals():
    return rows('deals', 'ORDER BY borrower_name')

@app.get('/api/deals/{deal_id}')
def deal_detail(deal_id: str):
    result = rows('deals', 'WHERE id = ?', (deal_id,))
    if not result:
        raise HTTPException(status_code=404, detail='Deal not found')
    return result[0]

@app.get('/api/deals/{deal_id}/stage-events')
def deal_stage_events(deal_id: str):
    ensure_deal(deal_id)
    return rows('stage_events', 'WHERE deal_id = ? ORDER BY entered_at ASC', (deal_id,))

@app.get('/api/deals/{deal_id}/bbc')
def deal_bbc(deal_id: str, limit: int = 10):
    ensure_deal(deal_id)
    safe_limit = max(1, min(limit, 100))
    result = rows('borrowing_base_certificates', 'WHERE deal_id = ? ORDER BY created_at DESC LIMIT ?', (deal_id, safe_limit))
    return list(reversed(result))

@app.get('/api/deals/{deal_id}/pending-changes')
def deal_pending_changes(deal_id: str):
    ensure_deal(deal_id)
    return rows('pending_changes', 'WHERE deal_id = ? ORDER BY created_at DESC', (deal_id,))

@app.get('/api/documents')
def documents(deal_id: str | None = None):
    if deal_id:
        return rows('documents', 'WHERE deal_id = ? ORDER BY uploaded_at DESC', (deal_id,))
    return rows('documents', 'ORDER BY uploaded_at DESC')

@app.get('/api/audit')
def audit(deal_id: str | None = None):
    if deal_id:
        return rows('audit_log', 'WHERE deal_id = ? ORDER BY id DESC', (deal_id,))
    return rows('audit_log', 'ORDER BY id DESC')

@app.get('/api/pending-changes/roles')
def pending_roles():
    return ['Credit Officer', 'Portfolio Manager', 'Operations Analyst', 'Relationship Manager']

@app.get('/api/pending-changes')
def pending_changes(status: str | None = None, deal_id: str | None = None):
    query = 'SELECT * FROM pending_changes'
    filters = []
    values = []
    if status:
        filters.append('status = ?'); values.append(status)
    if deal_id:
        filters.append('deal_id = ?'); values.append(deal_id)
    if filters: query += ' WHERE ' + ' AND '.join(filters)
    query += ' ORDER BY created_at DESC'
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, values).fetchall()]

@app.get('/api/dashboard')
def dashboard():
    deal_rows = rows('deals', 'ORDER BY borrower_name')
    document_rows = rows('documents', 'ORDER BY uploaded_at DESC')
    return {'deals': deal_rows, 'documents': document_rows, 'deal_count': len(deal_rows), 'document_count': len(document_rows)}

__all__ = ['app']
