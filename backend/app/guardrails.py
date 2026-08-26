"""Guardrail evaluation for every proposed change entering the HITL queue.

A guardrail never silently blocks or silently auto-approves -- it attaches a
status and a required authority level to the PendingChange, and the approval
endpoint enforces both before a change can be committed. Four possible
outcomes:

  pass                    -- any approver at the deal's baseline authority may approve.
  warn                    -- approvable at baseline authority, but the reviewer sees why it's flagged.
  requires_elevated_approval -- only an approver whose role meets `required_authority` may approve.
  blocked                 -- cannot be approved at all unless the reviewer explicitly overrides,
                              which itself requires elevated authority and a recorded justification.
"""
from __future__ import annotations

from dataclasses import dataclass

ROLE_RANK = {
    "Relationship Manager": 1,
    "Loan Operations": 1,
    "Credit Officer": 2,
    "Portfolio Manager": 2,
    "Senior Credit Officer": 3,
    "Special Assets Officer": 3,
    "Risk Committee": 4,
    "Chief Credit Officer": 4,
}

ALL_ROLES = list(ROLE_RANK.keys())

RATING_ORDER = ["Pass", "Special Mention", "Substandard", "Doubtful", "Loss"]


def role_meets(role: str, required: str) -> bool:
    if not required:
        return True
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(required, 99)


@dataclass
class GuardrailResult:
    status: str
    notes: str
    required_authority: str


def evaluate(
    change_type: str,
    field_path: str,
    old_value: str,
    new_value: str,
    deal_authority_level: str,
    context: dict | None = None,
) -> GuardrailResult:
    context = context or {}

    if change_type == "draw_funding":
        available = context.get("available_before_draw")
        requested = context.get("requested_draw")
        if available is not None and requested is not None and requested > available:
            overage = requested - available
            return GuardrailResult(
                status="blocked",
                notes=(
                    f"Requested draw of ${requested:,.0f} exceeds available borrowing base capacity by "
                    f"${overage:,.0f}, which would create an overadvance. Blocked pending an explicit, "
                    f"justified override at Senior Credit Officer level or above."
                ),
                required_authority="Senior Credit Officer",
            )
        return GuardrailResult("pass", "Draw is within the calculated borrowing base.", deal_authority_level)

    if change_type == "risk_rating":
        try:
            old_idx = RATING_ORDER.index(old_value)
            new_idx = RATING_ORDER.index(new_value)
        except ValueError:
            old_idx, new_idx = 0, 0
        delta = new_idx - old_idx
        if delta >= 2:
            return GuardrailResult(
                status="requires_elevated_approval",
                notes=f"Multi-notch downgrade ({old_value} -> {new_value}) requires senior sign-off per the delegated authority matrix.",
                required_authority="Senior Credit Officer",
            )
        if delta == 1 and new_value in ("Substandard", "Doubtful", "Loss"):
            return GuardrailResult(
                status="requires_elevated_approval",
                notes=f"Downgrade into a classified category ({new_value}) requires senior sign-off.",
                required_authority="Senior Credit Officer",
            )
        if delta >= 1:
            return GuardrailResult(
                status="requires_elevated_approval",
                notes=f"Risk rating downgrade ({old_value} -> {new_value}) requires Credit Officer approval or above.",
                required_authority="Credit Officer",
            )
        return GuardrailResult("pass", "Rating change is stable or an upgrade.", deal_authority_level)

    if change_type == "watchlist" and str(new_value).lower() == "true":
        return GuardrailResult(
            status="requires_elevated_approval",
            notes="Watchlist migration triggers enhanced monitoring and reporting; requires Credit Officer approval or above.",
            required_authority="Credit Officer",
        )

    if change_type == "covenant_result" and "breach" in str(new_value).lower():
        return GuardrailResult(
            status="requires_elevated_approval",
            notes="A covenant breach requires Senior Credit Officer review before a waiver, cure, or default remedy path is chosen.",
            required_authority="Senior Credit Officer",
        )

    if change_type == "document_intake":
        confidence = context.get("confidence", 1.0)
        if confidence < 0.5:
            return GuardrailResult(
                status="warn",
                notes=f"Low-confidence extraction ({confidence:.0%}); verify against the source document before approving.",
                required_authority=deal_authority_level,
            )
        return GuardrailResult("pass", "Extraction confidence is acceptable.", deal_authority_level)

    if change_type == "field_update":
        try:
            old_f, new_f = float(old_value), float(new_value)
            if old_f and abs(new_f - old_f) / abs(old_f) > 0.10:
                return GuardrailResult(
                    status="warn",
                    notes=f"Proposed value changes {field_path} by more than 10% ({old_value} -> {new_value}); confirm against source data.",
                    required_authority=deal_authority_level,
                )
        except (TypeError, ValueError):
            pass
        return GuardrailResult("pass", "Within normal variance.", deal_authority_level)

    return GuardrailResult("pass", "No specific guardrail rule matched; standard approval applies.", deal_authority_level)
