from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, crud, guardrails, schemas
from ..db import get_db
from ..models import PendingChange

router = APIRouter(prefix="/api/pending-changes", tags=["hitl"])


@router.get("", response_model=list[schemas.PendingChangeOut])
def list_pending_changes(status: str | None = None, deal_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(PendingChange)
    if status:
        q = q.filter(PendingChange.status == status)
    if deal_id:
        q = q.filter(PendingChange.deal_id == deal_id)
    return q.order_by(PendingChange.created_at.desc()).all()


@router.get("/roles", response_model=list[str])
def list_roles():
    return guardrails.ALL_ROLES


@router.post("/{change_id}/decision", response_model=schemas.PendingChangeOut)
def decide(change_id: str, decision: schemas.ApprovalDecision, db: Session = Depends(get_db)):
    change = db.get(PendingChange, change_id)
    if not change:
        raise HTTPException(404, "Pending change not found")
    if change.status != "pending":
        raise HTTPException(409, f"This change was already {change.status}.")

    deal = crud.get_deal_or_404(db, change.deal_id)

    if not decision.approve:
        change.status = "rejected"
        change.decided_by = decision.decided_by
        change.decided_role = decision.role
        change.decision_notes = decision.notes
        change.decided_at = datetime.now(timezone.utc)
        audit.append(
            db, event_type="human_rejection", actor=decision.decided_by, deal_id=deal.id, stage=change.stage,
            summary=f"Rejected: {change.field_path} -> {change.new_value}",
            detail={"change_id": change.id, "role": decision.role, "notes": decision.notes},
        )
        db.commit()
        db.refresh(change)
        return change

    if change.guardrail_status == "blocked":
        if not decision.override:
            raise HTTPException(409, "This change is blocked by a guardrail. Approval requires an explicit override with a justification.")
        if not guardrails.role_meets(decision.role, change.required_authority):
            raise HTTPException(403, f"Overriding this guardrail requires {change.required_authority} authority or above.")
        if not decision.notes.strip():
            raise HTTPException(400, "An override requires a written justification in the decision notes.")
    elif change.guardrail_status == "requires_elevated_approval":
        if not guardrails.role_meets(decision.role, change.required_authority):
            raise HTTPException(403, f"This change requires {change.required_authority} authority or above.")

    crud.apply_pending_change(db, deal, change)

    change.status = "approved"
    change.decided_by = decision.decided_by
    change.decided_role = decision.role
    change.decision_notes = decision.notes
    change.override_used = decision.override and change.guardrail_status == "blocked"
    change.decided_at = datetime.now(timezone.utc)

    audit.append(
        db, event_type="human_approval", actor=decision.decided_by, deal_id=deal.id, stage=change.stage,
        summary=f"Approved: {change.field_path} -> {change.new_value}" + (" (guardrail override)" if change.override_used else ""),
        detail={
            "change_id": change.id, "role": decision.role, "notes": decision.notes,
            "guardrail_status": change.guardrail_status, "override_used": change.override_used,
        },
    )
    db.commit()
    db.refresh(change)
    return change
