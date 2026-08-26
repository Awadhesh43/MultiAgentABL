from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import audit, crud, recommendations, schemas
from ..db import get_db
from ..models import BorrowingBaseCertificate, PendingChange, StageEvent

router = APIRouter(prefix="/api/deals", tags=["agents"])

STAGE_LABELS = {
    "origination": "01 - Origination & Prospecting",
    "underwriting": "02 - Underwriting & Credit Approval",
    "documentation_closing": "03-04 - Structuring, Documentation & Closing",
    "boarding": "05 - Boarding & Onboarding",
    "borrowing_base": "06 - Servicing & Collateral Monitoring",
    "field_exam": "07 - Field Exams & Appraisals",
    "covenant_compliance": "08 - Covenant Compliance & Financial Reporting",
    "portfolio_risk": "09 - Portfolio & Risk Monitoring",
    "renewal_amendment": "10 - Renewal, Amendment & Annual Review",
    "special_assets_workout": "Branch - Special Assets, Default & Workout",
}

# The standard sequential path a deal moves through. special_assets_workout
# is a branch, not a rung on this ladder -- a deal only reaches it via an
# agent/human decision (see seed.py's mark_timeline(..., branch=...)), and
# this generic "move to the next rung" action deliberately doesn't try to
# guess a way back out of it.
LIFECYCLE_ORDER = [
    "origination", "underwriting", "documentation_closing", "boarding",
    "borrowing_base", "field_exam", "covenant_compliance", "portfolio_risk",
    "renewal_amendment",
]


@router.post("/{deal_id}/stages/{stage_id}/run", response_model=schemas.StageRunResponse)
def run_stage(deal_id: str, stage_id: str, req: schemas.StageRunRequest, db: Session = Depends(get_db)):
    deal = crud.get_deal_or_404(db, deal_id)
    stage_label = STAGE_LABELS.get(stage_id, stage_id)

    recent_bbcs = (
        db.query(BorrowingBaseCertificate)
        .filter(BorrowingBaseCertificate.deal_id == deal_id)
        .order_by(BorrowingBaseCertificate.created_at.asc())
        .all()[-5:]
    )

    rec = recommendations.run_stage(deal, stage_id, recent_bbcs, req.extra_context)

    existing = (
        db.query(StageEvent)
        .filter(StageEvent.deal_id == deal_id, StageEvent.stage == stage_id)
        .first()
    )
    if not existing:
        db.add(StageEvent(deal_id=deal_id, stage=stage_id, status="in_progress", notes=rec["text"][:280]))

    audit.append(
        db, event_type="stage_reviewed", actor=rec["agent_name"], deal_id=deal.id, stage=stage_label,
        summary=rec["text"][:280], detail={"source": rec["source"]},
    )

    created = []
    for pc in rec["proposed_changes"]:
        created.append(
            crud.create_pending_change(
                db, deal, stage=stage_label, change_type=pc["change_type"], field_path=pc["field_path"],
                new_value=str(pc["new_value"]), rationale=pc["rationale"], proposed_by=rec["agent_name"],
            )
        )

    db.commit()
    return schemas.StageRunResponse(
        stage=stage_label, agent_name=rec["agent_name"], text=rec["text"], citations=rec["citations"],
        source=rec["source"], pending_changes=[schemas.PendingChangeOut.model_validate(c) for c in created],
    )


@router.post("/{deal_id}/advance-stage", response_model=schemas.AdvanceStageResponse)
def advance_stage(deal_id: str, body: schemas.AdvanceStageRequest, db: Session = Depends(get_db)):
    """Moves a deal from its current stage to the next one in LIFECYCLE_ORDER.

    This is the one action in the app that changes `deal.stage` -- running a
    stage agent (above) never does, on purpose, since a recommendation isn't
    the same thing as the deal actually having moved forward. Advancing is
    blocked, with a specific count, while any HITL item tied to the current
    stage is still pending: that's the whole point of the queue -- a stage
    isn't done until a human has acted on everything it produced.
    """
    deal = crud.get_deal_or_404(db, deal_id)
    current_stage = deal.stage
    current_label = STAGE_LABELS.get(current_stage, current_stage)

    if current_stage not in LIFECYCLE_ORDER:
        raise HTTPException(
            409,
            f"'{current_label}' isn't part of the standard sequence (e.g. the special assets/workout "
            "branch), so it has no automatic 'next stage' -- move this deal by proposing a stage change directly.",
        )

    idx = LIFECYCLE_ORDER.index(current_stage)
    if idx == len(LIFECYCLE_ORDER) - 1:
        raise HTTPException(409, f"'{current_label}' is already the final stage in the standard sequence.")

    pending_count = (
        db.query(PendingChange)
        .filter(PendingChange.deal_id == deal_id, PendingChange.stage == current_label, PendingChange.status == "pending")
        .count()
    )
    if pending_count:
        raise HTTPException(
            409,
            f"{pending_count} pending approval(s) at '{current_label}' must be resolved before this deal can advance.",
        )

    next_stage = LIFECYCLE_ORDER[idx + 1]
    next_label = STAGE_LABELS.get(next_stage, next_stage)
    now = datetime.now(timezone.utc)

    current_event = db.query(StageEvent).filter(StageEvent.deal_id == deal_id, StageEvent.stage == current_stage).first()
    if current_event:
        current_event.status = "completed"
        current_event.completed_at = now
    else:
        db.add(StageEvent(deal_id=deal_id, stage=current_stage, status="completed", entered_at=now, completed_at=now))

    next_event = db.query(StageEvent).filter(StageEvent.deal_id == deal_id, StageEvent.stage == next_stage).first()
    if next_event:
        next_event.status = "in_progress"
    else:
        db.add(StageEvent(deal_id=deal_id, stage=next_stage, status="in_progress", entered_at=now))

    deal.stage = next_stage

    audit.append(
        db, event_type="stage_advanced", actor=body.decided_by, deal_id=deal_id, stage=next_label,
        summary=f"Advanced from '{current_label}' to '{next_label}'",
        detail={"from_stage": current_stage, "to_stage": next_stage, "decided_by": body.decided_by},
    )

    db.commit()
    return schemas.AdvanceStageResponse(from_stage=current_stage, to_stage=next_stage, to_stage_label=next_label)
