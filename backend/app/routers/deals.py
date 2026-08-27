from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from abl_agents import calculations

from .. import audit, crud, schemas
from ..db import get_db
from ..models import BorrowingBaseCertificate, Deal, StageEvent

router = APIRouter(prefix="/api/deals", tags=["deals"])


def _slugify(text: str, max_len: int = 30) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "deal"


@router.get("", response_model=list[schemas.DealSummary])
def list_deals(db: Session = Depends(get_db)):
    return db.query(Deal).order_by(Deal.borrower_name).all()


@router.post("", response_model=schemas.DealDetail)
def create_deal(body: schemas.DealCreate, db: Session = Depends(get_db)):
    """Origination intake: the only fields a new deal starts with are what a
    relationship manager actually knows on day one -- who the borrower is,
    what to call the deal, roughly what they're asking for, and (if this
    borrower already has a deal on file) its industry. Everything else
    (advance rates, financials, risk rating) takes its column default, the
    same starting point Harbor Steel Fabricators -- the seeded
    origination-stage deal -- has, and gets filled in as the deal moves
    through underwriting and closing.
    """
    borrower_name = body.borrower_name.strip()
    if not borrower_name:
        raise HTTPException(400, "Borrower name is required.")
    deal_name = body.deal_name.strip()
    if not deal_name:
        raise HTTPException(400, "Deal name is required.")
    if body.commitment <= 0:
        raise HTTPException(400, "Requested / commitment amount must be greater than zero.")

    industry = body.industry.strip() or "Not yet specified"
    deal_id = f"{_slugify(borrower_name)}-{uuid.uuid4().hex[:6]}"

    deal = Deal(
        id=deal_id,
        borrower_name=borrower_name,
        deal_name=deal_name,
        industry=industry,
        commitment=body.commitment,
        stage="origination",
    )
    db.add(deal)
    db.flush()  # assigns created_at/updated_at defaults before the audit entry references deal.id

    db.add(StageEvent(deal_id=deal.id, stage="origination", status="in_progress"))

    audit.append(
        db, event_type="deal_created", actor=body.created_by, deal_id=deal.id,
        stage="01 - Origination & Prospecting",
        summary=f"Created new deal '{deal_name}' for {borrower_name} -- requested commitment ${body.commitment:,.0f}",
        detail={"deal_id": deal.id, "borrower_name": borrower_name, "deal_name": deal_name, "industry": industry, "commitment": body.commitment},
    )

    db.commit()
    db.refresh(deal)
    return deal


@router.get("/{deal_id}", response_model=schemas.DealDetail)
def get_deal(deal_id: str, db: Session = Depends(get_db)):
    return crud.get_deal_or_404(db, deal_id)


@router.get("/{deal_id}/stage-events", response_model=list[schemas.StageEventOut])
def get_stage_events(deal_id: str, db: Session = Depends(get_db)):
    crud.get_deal_or_404(db, deal_id)
    return (
        db.query(StageEvent)
        .filter(StageEvent.deal_id == deal_id)
        .order_by(StageEvent.entered_at.asc())
        .all()
    )


@router.get("/{deal_id}/bbc", response_model=list[schemas.BBCOut])
def get_bbc_history(deal_id: str, limit: int = 10, db: Session = Depends(get_db)):
    crud.get_deal_or_404(db, deal_id)
    return (
        db.query(BorrowingBaseCertificate)
        .filter(BorrowingBaseCertificate.deal_id == deal_id)
        .order_by(BorrowingBaseCertificate.created_at.asc())
        .all()[-limit:]
    )


@router.get("/{deal_id}/pending-changes", response_model=list[schemas.PendingChangeOut])
def get_deal_pending_changes(deal_id: str, db: Session = Depends(get_db)):
    from ..models import PendingChange

    crud.get_deal_or_404(db, deal_id)
    return (
        db.query(PendingChange)
        .filter(PendingChange.deal_id == deal_id)
        .order_by(PendingChange.created_at.desc())
        .all()
    )


@router.post("/{deal_id}/bbc/submit", response_model=dict)
def submit_bbc(deal_id: str, submission: schemas.BBCSubmissionIn, db: Session = Depends(get_db)):
    deal = crud.get_deal_or_404(db, deal_id)

    result = calculations.calculate_borrowing_base(
        gross_ar=submission.gross_ar,
        ar_ineligibles=submission.ar_ineligibles,
        ar_advance_rate=deal.ar_advance_rate,
        inventory_at_cost=submission.inventory_at_cost,
        ineligible_inventory=submission.ineligible_inventory,
        nolv_pct_of_cost=submission.nolv_pct_of_cost,
        inventory_advance_rate_nolv=deal.inventory_advance_rate_nolv,
        inventory_cost_cap_pct=deal.inventory_cost_cap_pct,
        trailing_gross_sales=submission.trailing_gross_sales,
        trailing_credits_discounts_writeoffs=submission.trailing_credits_discounts_writeoffs,
        dilution_threshold_pct=deal.dilution_threshold_pct,
        rent_reserve=submission.rent_reserve,
        facility_commitment=deal.commitment,
        outstanding_balance=deal.outstanding_balance,
        letters_of_credit=deal.letters_of_credit,
        excess_availability_trigger_pct=deal.excess_availability_trigger_pct,
        excess_availability_trigger_floor=deal.excess_availability_trigger_floor,
        requested_draw=submission.requested_draw,
    )

    note = ""
    if result.springing_trigger_breached:
        note = "Excess availability trigger breached this period -- springing cash dominion and FCCR testing apply."

    bbc = BorrowingBaseCertificate(
        deal_id=deal.id, period_end=submission.period_end, gross_ar=result.gross_ar,
        eligible_ar=result.eligible_ar, ar_availability=result.ar_availability,
        inventory_at_cost=result.inventory_at_cost, eligible_inventory_at_cost=result.eligible_inventory_at_cost,
        inventory_availability=result.inventory_availability, dilution_pct=result.dilution_pct,
        dilution_reserve=result.dilution_reserve, rent_reserve=result.rent_reserve,
        borrowing_base=result.borrowing_base, outstanding_balance=deal.outstanding_balance,
        letters_of_credit=deal.letters_of_credit, availability=result.availability,
        cash_dominion_active=result.springing_trigger_breached, fccr_tested=result.springing_trigger_breached,
        note=note,
    )
    db.add(bbc)
    db.flush()

    from .. import audit

    audit.append(
        db, event_type="bbc_processed", actor=submission.proposed_by, deal_id=deal.id, stage="borrowing_base",
        summary=f"BBC processed for period {submission.period_end}: availability ${result.availability:,.0f}",
        detail=result.to_dict(),
    )

    changes = [
        crud.create_pending_change(
            db, deal, stage="borrowing_base", change_type="field_update", field_path="latest_borrowing_base",
            new_value=str(round(result.borrowing_base, 2)), proposed_by=submission.proposed_by,
            rationale=f"Recomputed from the {submission.period_end} BBC submission.",
        ),
        crud.create_pending_change(
            db, deal, stage="borrowing_base", change_type="field_update", field_path="latest_availability",
            new_value=str(round(result.availability, 2)), proposed_by=submission.proposed_by,
            rationale=(note or f"Recomputed from the {submission.period_end} BBC submission.") ,
        ),
    ]

    if submission.requested_draw:
        new_balance = deal.outstanding_balance + submission.requested_draw
        changes.append(
            crud.create_pending_change(
                db, deal, stage="borrowing_base", change_type="draw_funding", field_path="outstanding_balance",
                new_value=str(round(new_balance, 2)), proposed_by=submission.proposed_by,
                rationale=f"Requested incremental draw of ${submission.requested_draw:,.0f} against this period's certificate.",
                context={"available_before_draw": result.availability, "requested_draw": submission.requested_draw},
            )
        )

    db.commit()
    return {
        "bbc": schemas.BBCOut.model_validate(bbc),
        "calculation": result.to_dict(),
        "pending_changes": [schemas.PendingChangeOut.model_validate(c) for c in changes],
    }
