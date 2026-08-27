<<<<<<< HEAD
import os
import shutil
import sqlite3
import sys
from pathlib import Path

=======
from pathlib import Path
import shutil
import sqlite3
>>>>>>> 742be42 (feat: add new FastAPI backend and Vercel configuration for Agentic ABL Platform)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
<<<<<<< HEAD
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
=======
RUNTIME = Path('/tmp/abl-platform')
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
        return [dict(r) for r in conn.execute(f'SELECT * FROM {table} {where} {order}', params).fetchall()]

def ensure_deal(deal_id):
    result = rows('deals', 'WHERE id = ?', (deal_id,))
    if not result:
        raise HTTPException(404, 'Deal not found')
    return result[0]
>>>>>>> 742be42 (feat: add new FastAPI backend and Vercel configuration for Agentic ABL Platform)

@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': DB.exists()}

<<<<<<< HEAD
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
=======
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
    return rows('borrowing_base_certificates', 'WHERE deal_id = ?', (deal_id,), f'ORDER BY created_at DESC LIMIT {max(1, min(limit, 100))}')
>>>>>>> 742be42 (feat: add new FastAPI backend and Vercel configuration for Agentic ABL Platform)

@app.get('/api/deals/{deal_id}/pending-changes')
def deal_pending_changes(deal_id: str):
    ensure_deal(deal_id)
<<<<<<< HEAD
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
=======
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
>>>>>>> 742be42 (feat: add new FastAPI backend and Vercel configuration for Agentic ABL Platform)
