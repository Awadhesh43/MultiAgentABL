from pathlib import Path
import os
import re
import hashlib
import json
import shutil
import sqlite3
import ssl
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from types import SimpleNamespace

from app import config, schemas, recommendations
from app import knowledge_base

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path('/tmp/abl-platform') if os.environ.get('VERCEL') else ROOT
RUNTIME.mkdir(parents=True, exist_ok=True)
SOURCE_DB = ROOT / 'abl_platform.db'
DB = RUNTIME / 'abl_platform.db'
if SOURCE_DB.exists() and (not DB.exists() or DB.stat().st_size == 0):
    shutil.copyfile(SOURCE_DB, DB)

app = FastAPI(title='Agentic ABL Platform API', version='0.1.0')
DATABASE_URL = next((os.environ.get(name) for name in ('POSTGRES_URL', 'DATABASE_URL', 'POSTGRES_PRISMA_URL', 'POSTGRES_URL_NON_POOLING') if (os.environ.get(name) or '').strip().strip('"').strip("'").startswith(('postgres://', 'postgresql://'))), None)
if not DATABASE_URL:
    raise RuntimeError('A Neon PostgreSQL connection variable must be configured')
DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+pg8000://', 1)
elif DATABASE_URL.startswith('postgresql://') and '+pg8000' not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+pg8000://', 1)
_parts = urlsplit(DATABASE_URL)
_query = [(key, value) for key, value in parse_qsl(_parts.query, keep_blank_values=True) if key.lower() not in {'sslmode', 'channel_binding', 'ssl_context', 'connect_timeout'}]
DATABASE_URL = urlunsplit((_parts.scheme, _parts.netloc, _parts.path, urlencode(_query), _parts.fragment))
NEON_ENGINE = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={'ssl_context': ssl.create_default_context()},
)


def ensure_neon_schema():
    with NEON_ENGINE.begin() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY, borrower_name TEXT NOT NULL, deal_name TEXT NOT NULL,
            industry TEXT NOT NULL DEFAULT 'Not yet specified', naics TEXT NOT NULL DEFAULT '', hq TEXT NOT NULL DEFAULT '', sponsor TEXT NOT NULL DEFAULT '',
            facility_type TEXT NOT NULL DEFAULT 'Senior secured ABL revolver', commitment DOUBLE PRECISION NOT NULL,
            closing_date TEXT NOT NULL DEFAULT '', maturity_date TEXT NOT NULL DEFAULT '', ar_advance_rate DOUBLE PRECISION NOT NULL DEFAULT 0.85,
            inventory_advance_rate_nolv DOUBLE PRECISION NOT NULL DEFAULT 0.85, inventory_cost_cap_pct DOUBLE PRECISION NOT NULL DEFAULT 0.60,
            dilution_threshold_pct DOUBLE PRECISION NOT NULL DEFAULT 0.05, excess_availability_trigger_pct DOUBLE PRECISION NOT NULL DEFAULT 0.10,
            excess_availability_trigger_floor DOUBLE PRECISION NOT NULL DEFAULT 2000000, fccr_minimum DOUBLE PRECISION NOT NULL DEFAULT 1.10,
            stage TEXT NOT NULL DEFAULT 'origination', risk_rating TEXT NOT NULL DEFAULT 'Pass', watchlist INTEGER NOT NULL DEFAULT 0,
            covenant_status TEXT NOT NULL DEFAULT 'not_yet_tested', outstanding_balance DOUBLE PRECISION NOT NULL DEFAULT 0, letters_of_credit DOUBLE PRECISION NOT NULL DEFAULT 0,
            latest_borrowing_base DOUBLE PRECISION NOT NULL DEFAULT 0, latest_availability DOUBLE PRECISION NOT NULL DEFAULT 0, trailing_revenue DOUBLE PRECISION NOT NULL DEFAULT 0,
            trailing_ebitda DOUBLE PRECISION NOT NULL DEFAULT 0, unfinanced_capex DOUBLE PRECISION NOT NULL DEFAULT 0, cash_taxes_paid DOUBLE PRECISION NOT NULL DEFAULT 0,
            distributions DOUBLE PRECISION NOT NULL DEFAULT 0, scheduled_debt_service DOUBLE PRECISION NOT NULL DEFAULT 0, annual_rent_and_leases DOUBLE PRECISION NOT NULL DEFAULT 0,
            authority_level TEXT NOT NULL DEFAULT 'Credit Officer', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS stage_events (
            id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', entered_at TEXT NOT NULL)'''))


def neon_rows(sql: str, params: dict | None = None):
    with NEON_ENGINE.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]


def neon_one(sql: str, params: dict):
    with NEON_ENGINE.connect() as conn:
        row = conn.execute(text(sql), params).mappings().first()
        return dict(row) if row else None
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])

@app.post('/api/wiki/chat', response_model=schemas.WikiChatResponse)
def wiki_chat(req: schemas.WikiChatRequest):
    scope_terms = {
        'abl', 'asset', 'based', 'borrowing', 'base', 'advance', 'availability',
        'receivables', 'inventory', 'collateral', 'covenant', 'field', 'exam',
        'appraisal', 'dilution', 'dominator', 'lender', 'facility', 'revolver',
        'working', 'capital', 'perfection', 'eligibility', 'risk', 'rating',
        'monitoring', 'compliance', 'borrowing-base',
    }
    question_terms = set(re.findall(r'[a-z0-9-]+', req.question.lower()))
    if not question_terms.intersection(scope_terms):
        return schemas.WikiChatResponse(
            answer="I can only answer questions about asset-based lending (ABL) and the bank's curated ABL knowledge base. Please ask about borrowing bases, collateral, eligibility, covenants, field exams, or ABL governance.",
            citations=[], grounded=False,
        )
    try:
        hits = knowledge_base.search(req.question, n_results=4)
    except Exception:
        hits = []
    citations = [{'source': hit.source, 'title': hit.title} for hit in hits]
    if not hits:
        return schemas.WikiChatResponse(answer="I couldn't find anything in the knowledge base related to that question.", citations=[], grounded=False)
    context_block = '\\n\\n'.join(f'[{hit.source} - {hit.title}]\\n{hit.text}' for hit in hits)
    if config.ANTHROPIC_API_KEY:
        try:
            import anthropic
            response = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY).messages.create(
                model=config.DEFAULT_MODEL, max_tokens=600,
                system='You are the ABL Wiki agent. Answer strictly from the provided knowledge base excerpts.',
                messages=[{'role': 'user', 'content': f'Knowledge base excerpts:\\n\\n{context_block}\\n\\nQuestion: {req.question}'}],
            )
            answer = ''.join(block.text for block in response.content if getattr(block, 'type', '') == 'text')
            return schemas.WikiChatResponse(answer=answer, citations=citations, grounded=True)
        except Exception:
            pass
    return schemas.WikiChatResponse(answer=context_block, citations=citations, grounded=True)

def rows(table, where='', params=(), order=''):
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f'SELECT * FROM {table} {where} {order}', params).fetchall()]

def ensure_deal(deal_id: str):
    result = neon_one('SELECT * FROM deals WHERE id = :id', {'id': deal_id})
    if not result:
        raise HTTPException(404, 'Deal not found')
    return result

@app.get('/api/health')
def health():
    return {'status': 'ok', 'database': DB.exists()}

@app.get('/api/dashboard')
def dashboard():
    deals = neon_rows('SELECT * FROM deals ORDER BY borrower_name')
    documents = neon_rows('SELECT * FROM documents ORDER BY uploaded_at DESC')
    return {'deals': deals, 'documents': documents, 'deal_count': len(deals), 'document_count': len(documents)}

@app.get('/api/deals')
def list_deals():
    return neon_rows('SELECT * FROM deals ORDER BY borrower_name')

@app.post('/api/deals')
async def create_deal(request: Request):
    body = await request.json()
    borrower_name = str(body.get('borrower_name', '')).strip()
    deal_name = str(body.get('deal_name', '')).strip()
    industry = str(body.get('industry', '')).strip() or 'Not yet specified'
    commitment = float(body.get('commitment', 0) or 0)
    if not borrower_name or not deal_name or commitment <= 0:
        raise HTTPException(400, 'Borrower name, deal name, and a positive commitment are required')
    deal_id = f"{re.sub(r'[^a-z0-9]+', '-', borrower_name.lower()).strip('-')[:30] or 'deal'}-{uuid.uuid4().hex[:6]}"
    timestamp = datetime.now(timezone.utc).isoformat()
    params = {'id': deal_id, 'borrower_name': borrower_name, 'deal_name': deal_name, 'industry': industry,
              'naics': str(body.get('naics', '')), 'hq': str(body.get('hq', '')), 'sponsor': str(body.get('sponsor', '')),
              'facility_type': str(body.get('facility_type', 'Senior secured ABL revolver')), 'commitment': commitment,
              'closing_date': str(body.get('closing_date', '')), 'maturity_date': str(body.get('maturity_date', '')),
              'created_at': timestamp, 'updated_at': timestamp}
    with NEON_ENGINE.begin() as conn:
        conn.execute(text('''INSERT INTO deals (id, borrower_name, deal_name, industry, naics, hq, sponsor, facility_type,
            commitment, closing_date, maturity_date, created_at, updated_at) VALUES
            (:id, :borrower_name, :deal_name, :industry, :naics, :hq, :sponsor, :facility_type, :commitment,
            :closing_date, :maturity_date, :created_at, :updated_at)'''), params)
        conn.execute(text('''INSERT INTO stage_events (id, deal_id, stage, status, notes, entered_at)
            VALUES (:event_id, :deal_id, 'origination', 'in_progress', '', :entered_at)'''),
                     {'event_id': uuid.uuid4().hex[:12], 'deal_id': deal_id, 'entered_at': timestamp})
    return ensure_deal(deal_id)

@app.get('/api/deals/{deal_id}')
def get_deal(deal_id: str):
    return ensure_deal(deal_id)

@app.get('/api/deals/{deal_id}/stage-events')
def stage_events(deal_id: str):
    ensure_deal(deal_id)
    return neon_rows('SELECT * FROM stage_events WHERE deal_id = :deal_id ORDER BY entered_at ASC', {'deal_id': deal_id})

STAGE_FLOW = [
    ('origination', '01 - Origination & Prospecting'),
    ('underwriting', '02 - Underwriting & Structure'),
    ('documentation_closing', '03 - Documentation & Closing'),
    ('covenant_compliance', '04 - Covenant & Compliance'),
    ('field_exam', '05 - Field Exam & Monitoring'),
    ('workout_exit', '06 - Workout / Exit'),
]

@app.post('/api/deals/{deal_id}/stages/{stage_id}/run')
async def run_stage(deal_id: str, stage_id: str, request: Request):
    deal_row = ensure_deal(deal_id)
    stage = next((item for item in STAGE_FLOW if item[0] == stage_id), None)
    if not stage:
        raise HTTPException(404, 'Stage not found')
    body = await request.json()
    context = str(body.get('extra_context', '')).strip()

    # Use attribute-based records so the standalone function does not depend on
    # SQLAlchemy constructor behavior or serialize ORM internals into the prompt.
    required_deal_fields = {
        'id': deal_id, 'borrower_name': '', 'industry': '', 'stage': stage_id,
        'risk_rating': '', 'watchlist': False, 'commitment': 0, 'outstanding_balance': 0,
        'latest_borrowing_base': 0, 'latest_availability': 0, 'fccr_minimum': 0,
        'excess_availability_trigger_pct': 0, 'excess_availability_trigger_floor': 0,
        'trailing_revenue': 0, 'trailing_ebitda': 0, 'unfinanced_capex': 0,
        'cash_taxes_paid': 0, 'distributions': 0, 'scheduled_debt_service': 0,
        'annual_rent_and_leases': 0,
    }
    required_deal_fields.update({key: value for key, value in deal_row.items() if key in required_deal_fields})
    deal = SimpleNamespace(**required_deal_fields)
    bbc_rows = neon_rows(
        'SELECT period_end, availability, dilution_pct, borrowing_base FROM borrowing_base_certificates WHERE deal_id = :deal_id ORDER BY created_at ASC',
        {'deal_id': deal_id},
    )[-5:]
    recent_bbcs = [SimpleNamespace(**row) for row in bbc_rows]

    # The shared orchestrator selects the stage agent, retrieves relevant KB context,
    # and calls Anthropic using config.ANTHROPIC_API_KEY.
    try:
        result = recommendations.run_stage(deal, stage_id, recent_bbcs, context)
    except Exception as exc:
        print(f"[v0] Orchestrated stage agent failed: {type(exc).__name__}: {exc}")
        raise HTTPException(502, 'The selected ABL agent could not complete its Anthropic analysis.') from exc
    return {
        'stage': stage_id,
        'agent_name': result['agent_name'],
        'text': result['text'],
        'citations': result.get('citations', []),
        'source': result.get('source', 'llm'),
        'pending_changes': result.get('proposed_changes', []),
    }

@app.post('/api/deals/{deal_id}/advance-stage')
async def advance_stage(deal_id: str, request: Request):
    deal = ensure_deal(deal_id)
    current = deal.get('stage') or 'origination'
    index = next((i for i, item in enumerate(STAGE_FLOW) if item[0] == current), 0)
    if index >= len(STAGE_FLOW) - 1:
        raise HTTPException(409, 'Deal is already at the final stage')
    next_stage = STAGE_FLOW[index + 1][0]
    timestamp = datetime.now(timezone.utc).isoformat()
    with NEON_ENGINE.begin() as conn:
        conn.execute(text('UPDATE deals SET stage = :stage, updated_at = :updated_at WHERE id = :id'), {'stage': next_stage, 'updated_at': timestamp, 'id': deal_id})
        conn.execute(text('INSERT INTO stage_events (id, deal_id, stage, status, notes, entered_at) VALUES (:event_id, :deal_id, :stage, :status, :notes, :entered_at)'), {'event_id': uuid.uuid4().hex[:12], 'deal_id': deal_id, 'stage': next_stage, 'status': 'in_progress', 'notes': '', 'entered_at': timestamp})
    return {'from_stage': current, 'to_stage': next_stage, 'to_stage_label': STAGE_FLOW[index + 1][1]}

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

@app.get('/api/approvals')
def approvals(status: str | None = None, deal_id: str | None = None):
    """Compatibility alias for clients that call the approvals resource."""
    return pending_changes(status=status, deal_id=deal_id)

@app.get('/api/approvals/roles')
def approval_roles():
    return roles()

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
    document = rows('documents', 'WHERE id = ?', (document_id,))[0]
    document['extracted_fields'] = []
    return document

@app.get('/api/documents')
def documents(deal_id: str | None = None):
    documents = rows('documents', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY uploaded_at DESC') if deal_id else rows('documents', order='ORDER BY uploaded_at DESC')
    for document in documents:
        document.setdefault('extracted_fields', [])
    return documents

@app.get('/api/audit')
def audit(deal_id: str | None = None):
    return rows('audit_log', 'WHERE deal_id = ?', (deal_id,), 'ORDER BY id DESC') if deal_id else rows('audit_log', order='ORDER BY id DESC')

__all__ = ['app']
