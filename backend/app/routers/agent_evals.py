"""The agent eval view: every agent call, with its performance and quality metrics."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import agent_eval, audit, schemas
from ..db import get_db
from ..models import AgentCall, Deal, ExtractedField, KeyTerm, PendingChange

router = APIRouter(prefix="/api/agent-calls", tags=["agent-evals"])


def _query(db: Session, agent_kind: str | None, mode: str | None, status: str | None, deal_id: str | None):
    q = db.query(AgentCall)
    if agent_kind:
        q = q.filter(AgentCall.agent_kind == agent_kind)
    if mode:
        q = q.filter(AgentCall.mode == mode)
    if status:
        q = q.filter(AgentCall.status == status)
    if deal_id:
        q = q.filter(AgentCall.deal_id == deal_id)
    return q


def _deal_names(db: Session) -> dict[str, str]:
    return {row.id: row.borrower_name for row in db.query(Deal.id, Deal.borrower_name)}


def _to_out(call: AgentCall, accuracies: dict, names: dict[str, str], model_cls=schemas.AgentCallOut, **extra):
    accuracy, basis = accuracies[call.id]
    out = model_cls.model_validate(call, from_attributes=True)
    return out.model_copy(update={
        "accuracy": accuracy, "accuracy_basis": basis, "deal_name": names.get(call.deal_id or "", ""), **extra,
    })


@router.get("", response_model=list[schemas.AgentCallOut])
def list_calls(
    agent_kind: str | None = None, mode: str | None = None, status: str | None = None, deal_id: str | None = None,
    limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    calls = _query(db, agent_kind, mode, status, deal_id).order_by(AgentCall.created_at.desc()).offset(offset).limit(limit).all()
    accuracies = agent_eval.compute_accuracies(db, calls)
    names = _deal_names(db)
    return [_to_out(c, accuracies, names) for c in calls]


@router.get("/summary", response_model=schemas.AgentSummaryOut)
def summary(agent_kind: str | None = None, deal_id: str | None = None, db: Session = Depends(get_db)):
    calls = _query(db, agent_kind, None, None, deal_id).all()
    accuracies = agent_eval.compute_accuracies(db, calls)

    groups: dict[tuple[str, str], list[AgentCall]] = defaultdict(list)
    for c in calls:
        groups[(c.agent_kind, c.agent_name)].append(c)
    by_agent = [
        schemas.AgentGroupAggregate(agent_kind=kind, agent_name=name, **agent_eval.aggregate(members, accuracies))
        for (kind, name), members in sorted(groups.items())
    ]
    return schemas.AgentSummaryOut(overall=schemas.AgentAggregate(**agent_eval.aggregate(calls, accuracies)), by_agent=by_agent)


@router.get("/{call_id}", response_model=schemas.AgentCallDetailOut)
def get_call(call_id: str, db: Session = Depends(get_db)):
    call = db.get(AgentCall, call_id)
    if not call:
        raise HTTPException(404, "Agent call not found")
    accuracies = agent_eval.compute_accuracies(db, [call])

    intake_fields: list[schemas.IntakeFieldEval] = []
    if call.agent_kind == "document_intake" and call.document_id:
        fields = db.query(ExtractedField).filter(ExtractedField.document_id == call.document_id).order_by(ExtractedField.id).all()
        data_types = {t.id: t.data_type for t in db.query(KeyTerm).filter(KeyTerm.id.in_([f.key_term_id for f in fields]))} if fields else {}
        for f in fields:
            source = next((e for e in f.evidence if e.used), None)
            machine_value = f.original_value or f.extracted_value
            intake_fields.append(schemas.IntakeFieldEval(
                field_id=f.id, label=f.label, original_value=machine_value, value=f.extracted_value, status=f.status,
                confidence=f.confidence, match_method=f.match_method,
                page=source.chunk.page if source else None, section=source.chunk.section if source else "",
                grounded=(
                    agent_eval.value_supported(machine_value, data_types.get(f.key_term_id, "text"), source.chunk.text)
                    if source and machine_value else None
                ),
            ))

    proposed: list[schemas.ProposedChangeEval] = []
    ids = (call.details or {}).get("pending_change_ids", [])
    if ids:
        proposed = [
            schemas.ProposedChangeEval(id=pc.id, field_path=pc.field_path, new_value=pc.new_value, status=pc.status, guardrail_status=pc.guardrail_status)
            for pc in db.query(PendingChange).filter(PendingChange.id.in_(ids))
        ]

    return _to_out(
        call, accuracies, _deal_names(db), schemas.AgentCallDetailOut,
        output_summary=call.output_summary, human_notes=call.human_notes, details=call.details or {},
        intake_fields=intake_fields, proposed_changes=proposed,
    )


@router.patch("/{call_id}/rating", response_model=schemas.AgentCallOut)
def rate_call(call_id: str, body: schemas.AgentRatingIn, db: Session = Depends(get_db)):
    """A human's explicit verdict on one agent call. Recorded in the audit trail
    like any other human decision about an agent's output."""
    if body.rating not in ("up", "down", None):
        raise HTTPException(400, "rating must be 'up', 'down', or null to clear it.")
    call = db.get(AgentCall, call_id)
    if not call:
        raise HTTPException(404, "Agent call not found")

    call.human_rating = body.rating
    call.human_notes = body.notes
    call.rated_by = body.rated_by if body.rating else ""
    call.rated_at = datetime.now(timezone.utc) if body.rating else None
    audit.append(
        db, event_type="agent_call_rated", actor=body.rated_by, deal_id=call.deal_id or "",
        summary=f"{call.agent_name} call rated {'thumbs ' + body.rating if body.rating else 'cleared'}",
        detail={"agent_call_id": call.id, "rating": body.rating, "notes": body.notes},
    )
    db.commit()
    db.refresh(call)
    return _to_out(call, agent_eval.compute_accuracies(db, [call]), _deal_names(db))
