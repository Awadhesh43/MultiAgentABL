from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import audit, schemas
from ..db import get_db
from ..models import AuditLogEntry

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditEntryOut])
def list_audit(deal_id: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(AuditLogEntry)
    if deal_id:
        q = q.filter(AuditLogEntry.deal_id == deal_id)
    return q.order_by(AuditLogEntry.id.desc()).limit(limit).all()


@router.get("/verify", response_model=schemas.ChainStatus)
def verify(db: Session = Depends(get_db)):
    valid, broken_at, count = audit.verify_chain(db)
    return schemas.ChainStatus(valid=valid, broken_at_id=broken_at, entry_count=count)
