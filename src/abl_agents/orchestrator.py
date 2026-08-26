"""The supervisor: runs one agent against one deal and enforces the HITL gate.

This is deliberately not itself an LLM call. Routing which agent handles a
stage, and refusing to commit any proposed change without a human decision,
are both meant to be reliable and auditable -- so they are plain Python, not
something the model is trusted to get right on its own. This mirrors the
HLD's L2 orchestration layer: the supervisor holds state and enforces gates;
the agents underneath it do the reasoning.
"""
from __future__ import annotations

from typing import Callable, Optional

from . import audit_log, deal_store, registry
from .agent import AgentResult

ApproveFn = Callable[[str, dict], bool]

_STAGE_PROMPTS: dict[str, str] = {
    "origination": (
        "Review deal {deal_id} as a prospective/existing ABL relationship. Summarize the borrower's "
        "industry and collateral fit for an ABL structure and note anything about the current facility "
        "sizing or advance rates that looks aggressive or conservative for this collateral mix."
    ),
    "underwriting": (
        "Underwrite deal {deal_id}: pull the deal record and financials, compute FCCR from the on-file "
        "trailing financials, and give a risk-rating recommendation with rationale. If you believe the "
        "current on-file risk rating should change, use propose_change."
    ),
    "documentation_closing": (
        "Review deal {deal_id}'s facility terms (advance rates, ineligibles policy, reserves, covenants) "
        "for internal consistency with standard ABL structuring practice, and summarize what a closing "
        "checklist for a facility with these terms should confirm."
    ),
    "boarding": (
        "Confirm deal {deal_id} is correctly boarded for servicing: do the reporting cadence, covenant "
        "trigger definitions, and reserve policy on file look complete and internally consistent for "
        "ongoing borrowing base monitoring?"
    ),
    "borrowing_base": (
        "Deal {deal_id} has a new, not-yet-processed Borrowing Base Certificate submission. Fetch it with "
        "get_pending_bbc_submission, fetch recent history with get_bbc_history for trend context, then "
        "compute the resulting borrowing base and availability with calculate_borrowing_base (pass through "
        "the submission's requested_incremental_draw if present as requested_draw). Call out any dilution, "
        "concentration, or availability-trend concerns, and state plainly whether the requested draw is "
        "fundable in full."
    ),
    "field_exam": (
        "Review deal {deal_id}'s field exam and NOLV appraisal history against the risk-based cadence "
        "policy, and recommend whether the next exam or appraisal should be scheduled on the normal "
        "cycle or accelerated, given the deal's recent risk profile."
    ),
    "covenant_compliance": (
        "Test deal {deal_id}'s springing FCCR covenant for the current period. Use recent get_bbc_history "
        "data to determine whether excess availability has fallen below the springing trigger, compute "
        "FCCR, and use check_covenant_compliance to determine the result. Draft the substance of this "
        "period's compliance certificate finding."
    ),
    "portfolio_risk": (
        "Assess deal {deal_id} for early-warning signals: review the BBC history trend and field exam "
        "history, and recommend whether this credit should migrate onto the watchlist. If so, use "
        "propose_change to stage the watchlist flag and, if warranted, a risk rating change."
    ),
    "renewal_amendment": (
        "Prepare an annual review recommendation for deal {deal_id}: given current financials, FCCR, and "
        "appraisal trend, should advance rates, the facility commitment, or covenant levels change at the "
        "next renewal? State your recommendation clearly."
    ),
    "special_assets_workout": (
        "Deal {deal_id} has been referred to special assets. Summarize the deterioration on file that led "
        "here (BBC trend, covenant status, risk rating) and lay out forbearance vs. restructuring vs. "
        "liquidation considerations given the current collateral position."
    ),
}


def build_stage_prompt(agent_id: str, deal_id: str, extra_context: str = "") -> str:
    template = _STAGE_PROMPTS.get(agent_id, "Review deal {deal_id} for this stage of the ABL lifecycle.")
    prompt = template.format(deal_id=deal_id)
    if extra_context:
        prompt += f"\n\nAdditional context: {extra_context}"
    return prompt


class DealWorkflow:
    def __init__(self, deal_id: str):
        self.deal_id = deal_id

    def run_stage(
        self,
        agent_id: str,
        approve_fn: ApproveFn,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        extra_context: str = "",
    ) -> tuple[AgentResult, list[dict]]:
        agent = registry.get_agent(agent_id)
        stage_label = registry.get_stage_label(agent_id)
        prompt = build_stage_prompt(agent_id, self.deal_id, extra_context)

        result = agent.run(prompt, on_tool_call=on_tool_call)

        audit_log.append_entry(
            event_type="agent_recommendation",
            deal_id=self.deal_id,
            stage=stage_label,
            actor=agent.name,
            summary=result.text[:300],
            detail={
                "tool_call_count": len(result.tool_calls),
                "citations": result.citations,
                "pending_change_count": len(result.pending_changes),
            },
        )

        approved_changes = []
        for change in result.pending_changes:
            approved = approve_fn(agent.name, change)
            if approved:
                applied = deal_store.apply_change(
                    change["deal_id"], change["field_path"], change["new_value"]
                )
                audit_log.append_entry(
                    event_type="human_approval",
                    deal_id=self.deal_id,
                    stage=stage_label,
                    actor="human_reviewer",
                    summary=f"Approved: {change['field_path']} -> {change['new_value']}",
                    detail={"rationale": change["rationale"], "applied": applied, "proposed_by": agent.name},
                )
                approved_changes.append(change)
            else:
                audit_log.append_entry(
                    event_type="human_rejection",
                    deal_id=self.deal_id,
                    stage=stage_label,
                    actor="human_reviewer",
                    summary=f"Rejected: {change['field_path']} -> {change['new_value']}",
                    detail={"rationale": change["rationale"], "proposed_by": agent.name},
                )

        return result, approved_changes
