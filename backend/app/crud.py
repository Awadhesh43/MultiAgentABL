from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import audit, guardrails
from .models import Deal, PendingChange

_BOOL_FIELDS = {"watchlist"}
_FLOAT_FIELDS = {
    "outstanding_balance", "letters_of_credit", "latest_borrowing_base", "latest_availability",
    "trailing_revenue", "trailing_ebitda", "commitment", "unfinanced_capex", "cash_taxes_paid",
    "distributions", "scheduled_debt_service", "annual_rent_and_leases", "ar_advance_rate",
    "inventory_advance_rate_nolv", "inventory_cost_cap_pct", "dilution_threshold_pct",
    "excess_availability_trigger_pct", "excess_availability_trigger_floor", "fccr_minimum",
}


def get_deal_or_404(db: Session, deal_id: str) -> Deal:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(404, f"No deal with id {deal_id!r}")
    return deal


def create_pending_change(
    db: Session,
    deal: Deal,
    stage: str,
    change_type: str,
    field_path: str,
    new_value: str,
    rationale: str,
    proposed_by: str,
    context: dict | None = None,
) -> PendingChange:
    old_value = str(getattr(deal, field_path, "")) if hasattr(deal, field_path) else ""

    result = guardrails.evaluate(
        change_type=change_type,
        field_path=field_path,
        old_value=old_value,
        new_value=str(new_value),
        deal_authority_level=deal.authority_level,
        context=context,
    )

    change = PendingChange(
        deal_id=deal.id,
        stage=stage,
        change_type=change_type,
        field_path=field_path,
        old_value=old_value,
        new_value=str(new_value),
        rationale=rationale,
        proposed_by=proposed_by,
        guardrail_status=result.status,
        guardrail_notes=result.notes,
        required_authority=result.required_authority,
    )
    db.add(change)
    db.flush()

    audit.append(
        db, event_type="agent_recommendation" if "Agent" in proposed_by else "human_proposal",
        actor=proposed_by, deal_id=deal.id, stage=stage,
        summary=f"Proposed {field_path} -> {new_value}",
        detail={"change_id": change.id, "guardrail_status": result.status, "rationale": rationale},
    )
    return change


def apply_pending_change(db: Session, deal: Deal, change: PendingChange) -> None:
    field = change.field_path
    value: object = change.new_value
    if field in _BOOL_FIELDS:
        value = str(change.new_value).lower() == "true"
    elif field in _FLOAT_FIELDS:
        try:
            value = float(change.new_value)
        except ValueError:
            pass

    if hasattr(deal, field) and field not in ("id",):
        setattr(deal, field, value)
