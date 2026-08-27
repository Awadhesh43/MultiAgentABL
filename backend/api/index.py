from pathlib import Path
import os
import shutil
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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

@app.get('/api/document-types')
def document_types():
    types = rows('document_types', order='ORDER BY name')
    terms = rows('key_terms', order='ORDER BY created_at ASC')
    by_type = {}
    for term in terms:
        aliases = term.get('aliases', [])
        if isinstance(aliases, str):
            try: aliases = json.loads(aliases)
            except json.JSONDecodeError: aliases = []
        term['aliases'] = aliases
        by_type.setdefault(term['document_type_id'], []).append(term)
    for item in types:
        item['key_terms'] = by_type.get(item['id'], [])
    return types

@app.get('/api/audit/verify')
def verify_audit_chain():
    entries = rows('audit_log', order='ORDER BY id ASC')
    previous = '0' * 64
    for entry in entries:
        detail = entry.get('detail', {})
        if isinstance(detail, str):
            try: detail = json.loads(detail)
            except json.JSONDecodeError: detail = {}
        hashable = {
            'id': entry['id'], 'ts': entry['ts'], 'event_type': entry['event_type'],
            'deal_id': entry['deal_id'], 'stage': entry['stage'], 'actor': entry['actor'],
            'summary': entry['summary'], 'detail': detail, 'prev_hash': entry['prev_hash'],
        }
        digest = hashlib.sha256(json.dumps(hashable, sort_keys=True, default=str).encode()).hexdigest()
        if entry['prev_hash'] != previous or entry['hash'] != digest:
            return {'valid': False, 'broken_at_id': entry['id'], 'entry_count': len(entries)}
        previous = entry['hash']
    return {'valid': True, 'broken_at_id': None, 'entry_count': len(entries)}

@app.post('/api/documents/upload')
async def upload_document(
    file: UploadFile = File(...),
    document_type_id: str = Form(...),
    deal_id: str | None = Form(None),
    uploaded_by: str = Form('demo_user'),
):
    if not rows('document_types', 'WHERE id = ?', (document_type_id,)):
        raise HTTPException(404, 'Document type not found')
    if deal_id:
        ensure_deal(deal_id)
    content = await file.read()
    filename = file.filename or 'uploaded-document'
    document_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    safe_name = f'{document_id}_{Path(filename).name}'
    destination = RUNTIME / safe_name
    destination.write_bytes(content)
    excerpt = content.decode('utf-8', errors='ignore')[:3000]
    with sqlite3.connect(DB) as conn:
        conn.execute(
            'INSERT INTO documents (id, deal_id, document_type_id, filename, file_path, status, raw_text_excerpt, uploaded_at, uploaded_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (document_id, deal_id, document_type_id, filename, str(destination), 'pending_review', excerpt, timestamp, uploaded_by),
        )
        conn.commit()
    return rows('documents', 'WHERE id = ?', (document_id,))[0]

@app.get('/api/documents')
def documents(deal_id: str | None = None):
    return rows('documents', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY uploaded_at DESC') if deal_id else rows('documents', order='ORDER BY uploaded_at DESC')

@app.get('/api/audit')
def audit(deal_id: str | None = None):
    return rows('audit_log', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY id DESC') if deal_id else rows('audit_log', order='ORDER BY id DESC')

__all__ = ['app']
>>>>>>> origin/application-deployment
