"""Append-only, hash-chained audit trail, stored as rows in AuditLogEntry.

Same principle as the CLI demo's audit_log.py: each row embeds the hash of
the row before it, so the API can prove the log hasn't been edited or had
rows removed -- integrity is a property of the data, not of trusting the
application code that wrote it.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from .models import AuditLogEntry

GENESIS_HASH = "0" * 64


def _entry_hash(row: dict) -> str:
    payload = json.dumps(row, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def append(
    db: Session,
    event_type: str,
    actor: str,
    summary: str,
    deal_id: str = "",
    stage: str = "",
    detail: dict | None = None,
) -> AuditLogEntry:
    last = db.query(AuditLogEntry).order_by(AuditLogEntry.id.desc()).first()
    prev_hash = last.hash if last else GENESIS_HASH

    entry = AuditLogEntry(
        event_type=event_type,
        deal_id=deal_id,
        stage=stage,
        actor=actor,
        summary=summary,
        detail=detail or {},
        prev_hash=prev_hash,
        hash="",
    )
    db.add(entry)
    db.flush()  # assigns entry.id / entry.ts

    hashable = {
        "id": entry.id,
        "ts": entry.ts,
        "event_type": entry.event_type,
        "deal_id": entry.deal_id,
        "stage": entry.stage,
        "actor": entry.actor,
        "summary": entry.summary,
        "detail": entry.detail,
        "prev_hash": entry.prev_hash,
    }
    entry.hash = _entry_hash(hashable)
    db.flush()
    return entry


def verify_chain(db: Session) -> tuple[bool, int | None, int]:
    entries = db.query(AuditLogEntry).order_by(AuditLogEntry.id.asc()).all()
    prev = GENESIS_HASH
    for e in entries:
        hashable = {
            "id": e.id, "ts": e.ts, "event_type": e.event_type,
            "deal_id": e.deal_id, "stage": e.stage, "actor": e.actor,
            "summary": e.summary, "detail": e.detail, "prev_hash": e.prev_hash,
        }
        if e.prev_hash != prev or e.hash != _entry_hash(hashable):
            return False, e.id, len(entries)
        prev = e.hash
    return True, None, len(entries)
