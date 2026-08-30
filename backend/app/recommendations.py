"""Produces one stage recommendation for a deal: an LLM call when an API key
is configured, otherwise a deterministic rule-based fallback so the whole
HITL/guardrail flow stays demoable without any external dependency.

Reuses the system prompts from the CLI package's agent registry (src/abl_agents)
so the "advise, never decide" framing stays identical between the terminal
demo and the web app, and reuses calculations.py for anything numeric.
"""
from __future__ import annotations

import json

from abl_agents import calculations, knowledge_base

from . import config
from .models import BorrowingBaseCertificate, Deal

try:
    from abl_agents.registry import AGENT_DEFINITIONS

    _SYSTEM_PROMPTS = {d["id"]: d["system_prompt"] for d in AGENT_DEFINITIONS}
except Exception:  # pragma: no cover - registry import is best-effort
    _SYSTEM_PROMPTS = {}

_STAGE_KB_QUERY = {
    "origination": "ABL origination and collateral fit for a new relationship",
    "underwriting": "underwriting risk rating and collateral analysis",
    "documentation_closing": "credit agreement structuring and closing conditions precedent",
    "boarding": "boarding a facility for servicing and the covenant testing calendar",
    "field_exam": "field exam frequency and NOLV appraisal cadence",
    "covenant_compliance": "springing FCCR covenant testing and compliance certificate",
    "portfolio_risk": "watchlist migration triggers and early warning indicators",
    "renewal_amendment": "annual review and renewal advance rate considerations",
    "special_assets_workout": "special assets workout forbearance and liquidation",
}

_AGENT_NAMES = {
    "origination": "Origination Agent",
    "underwriting": "Underwriting & Credit Agent",
    "documentation_closing": "Documentation & Closing Agent",
    "boarding": "Boarding Agent",
    "field_exam": "Field Exam & Appraisal Agent",
    "covenant_compliance": "Covenant & Compliance Agent",
    "portfolio_risk": "Portfolio Risk & Early Warning Agent",
    "renewal_amendment": "Renewal & Amendment Agent",
    "special_assets_workout": "Special Assets / Workout Agent",
}

_SUBMIT_TOOL = {
    "name": "submit_recommendation",
    "description": "Submit your analysis and any proposed changes for this deal.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis": {"type": "string", "description": "3-6 sentence analysis grounded in the deal data and knowledge base excerpts provided."},
            "proposed_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "change_type": {"type": "string", "enum": ["field_update", "risk_rating", "watchlist", "covenant_result"]},
                        "field_path": {
                            "type": "string",
                            "description": (
                                "Must be one of: risk_rating, watchlist, outstanding_balance, "
                                "latest_borrowing_base, latest_availability, covenant_status, "
                                "trailing_ebitda, trailing_revenue."
                            ),
                        },
                        "new_value": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["change_type", "field_path", "new_value", "rationale"],
                },
            },
        },
        "required": ["analysis", "proposed_changes"],
    },
}


def _deal_context(deal: Deal, recent_bbcs: list[BorrowingBaseCertificate]) -> dict:
    return {
        "deal_id": getattr(deal, "id", ""),
        "borrower": getattr(deal, "borrower_name", ""),
        "industry": getattr(deal, "industry", ""),
        "stage": getattr(deal, "stage", ""),
        "risk_rating": getattr(deal, "risk_rating", ""),
        "watchlist": getattr(deal, "watchlist", False),
        "commitment": getattr(deal, "commitment", 0),
        "outstanding_balance": getattr(deal, "outstanding_balance", 0),
        "latest_borrowing_base": getattr(deal, "latest_borrowing_base", 0),
        "latest_availability": getattr(deal, "latest_availability", 0),
        "fccr_minimum": getattr(deal, "fccr_minimum", 0),
        "excess_availability_trigger_pct": getattr(deal, "excess_availability_trigger_pct", 0),
        "excess_availability_trigger_floor": getattr(deal, "excess_availability_trigger_floor", 0),
        "financials": {
            "trailing_revenue": getattr(deal, "trailing_revenue", 0),
            "trailing_ebitda": getattr(deal, "trailing_ebitda", 0),
            "unfinanced_capex": getattr(deal, "unfinanced_capex", 0),
            "cash_taxes_paid": getattr(deal, "cash_taxes_paid", 0),
            "distributions": getattr(deal, "distributions", 0),
            "scheduled_debt_service": getattr(deal, "scheduled_debt_service", 0),
            "annual_rent_and_leases": getattr(deal, "annual_rent_and_leases", 0),
        },
        "recent_bbc_history": [
            {
                "period_end": getattr(b, "period_end", ""), "availability": getattr(b, "availability", 0),
                "dilution_pct": getattr(b, "dilution_pct", 0), "borrowing_base": getattr(b, "borrowing_base", 0),
            }
            for b in recent_bbcs
        ],
    }


def run_stage(deal: Deal, stage_id: str, recent_bbcs: list[BorrowingBaseCertificate], extra_context: str = "") -> dict:
    """Run the selected lifecycle agent through Anthropic; never silently fall back."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is required for Run Agent")
    return _llm_recommend(deal, stage_id, recent_bbcs, extra_context)


def _llm_recommend(deal: Deal, stage_id: str, recent_bbcs: list[BorrowingBaseCertificate], extra_context: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    kb_hits = knowledge_base.search(_STAGE_KB_QUERY.get(stage_id, stage_id), n_results=3)
    kb_block = "\n\n".join(f"[{h.source} - {h.title}]\n{h.text}" for h in kb_hits)

    system_prompt = _SYSTEM_PROMPTS.get(
        stage_id,
        "You are an ABL lifecycle agent. You advise and draft; you never have standing authority to "
        "approve, fund, or change a deal record directly.",
    )
    ctx = _deal_context(deal, recent_bbcs)
    user_prompt = (
        f"Deal record:\n{json.dumps(ctx, indent=2, default=str)}\n\n"
        f"Relevant knowledge base excerpts:\n{kb_block}\n\n"
        f"{('Additional context: ' + extra_context) if extra_context else ''}\n\n"
        "Call submit_recommendation with your analysis and any proposed changes. If nothing should "
        "change, submit an empty proposed_changes list."
    )

    response = client.messages.create(
        model=config.DEFAULT_MODEL,
        max_tokens=1200,
        system=system_prompt,
        tools=[_SUBMIT_TOOL],
        tool_choice={"type": "tool", "name": "submit_recommendation"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    tool_block = next((b for b in response.content if getattr(b, "type", "") == "tool_use"), None)
    if tool_block is None:
        text_blocks = [getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"]
        payload = {"analysis": "".join(text_blocks), "proposed_changes": []}
    else:
        payload = tool_block.input if isinstance(tool_block.input, dict) else {}
    citations = [{"source": h.source, "title": h.title} for h in kb_hits]
    return {
        "agent_name": _AGENT_NAMES.get(stage_id, "ABL Agent"),
        "text": payload.get("analysis", ""),
        "citations": citations,
        "source": "llm",
        "proposed_changes": payload.get("proposed_changes", []),
    }


def _rule_based_recommend(deal: Deal, stage_id: str, recent_bbcs: list[BorrowingBaseCertificate]) -> dict:
    """Legacy deterministic helper retained for offline utilities; not used by Run Agent."""
    proposed: list[dict] = []

    if stage_id == "covenant_compliance":
        fccr = calculations.calculate_fccr(
            ebitda=deal.trailing_ebitda, unfinanced_capex=deal.unfinanced_capex,
            cash_taxes_paid=deal.cash_taxes_paid, distributions=deal.distributions,
            scheduled_debt_service=deal.scheduled_debt_service, annual_rent_and_leases=deal.annual_rent_and_leases,
        )
        trigger = max(deal.excess_availability_trigger_pct * deal.latest_borrowing_base, deal.excess_availability_trigger_floor)
        breached = deal.latest_availability < trigger
        result = calculations.check_covenant_compliance(fccr["fccr"], deal.fccr_minimum, breached)
        text = (
            f"FCCR computed at {fccr['fccr']:.2f}x. Excess availability trigger is ${trigger:,.0f}; "
            f"current availability is ${deal.latest_availability:,.0f}, so the covenant is "
            f"{'TESTED' if breached else 'dormant'} this period. {result['reason']}"
        )
        if breached:
            status_value = "in_compliance" if result["in_compliance"] else "breach"
            proposed.append({
                "change_type": "covenant_result", "field_path": "covenant_status",
                "new_value": status_value,
                "rationale": text,
            })
        return {"agent_name": _AGENT_NAMES.get(stage_id, "Covenant & Compliance Agent"), "text": text, "citations": [], "source": "rule_based", "proposed_changes": proposed}

    if stage_id == "portfolio_risk":
        declining = len(recent_bbcs) >= 3 and all(
            recent_bbcs[i].availability > recent_bbcs[i + 1].availability for i in range(len(recent_bbcs) - 2)
        )
        if declining and not deal.watchlist:
            text = (
                f"Availability has declined for {len(recent_bbcs)} consecutive periods on file "
                f"(most recent: ${recent_bbcs[-1].availability:,.0f}). This is a standard watchlist "
                f"migration trigger per the governance policy."
            )
            proposed.append({"change_type": "watchlist", "field_path": "watchlist", "new_value": "true", "rationale": text})
        elif deal.watchlist:
            text = "Deal is already on the watchlist; no further migration action needed this period."
        else:
            text = "No sustained decline detected in the on-file borrowing base history; no watchlist action recommended."
        return {"agent_name": _AGENT_NAMES.get(stage_id, "Portfolio Risk & Early Warning Agent"), "text": text, "citations": [], "source": "rule_based", "proposed_changes": proposed}

    if stage_id == "underwriting":
        fccr = calculations.calculate_fccr(
            ebitda=deal.trailing_ebitda, unfinanced_capex=deal.unfinanced_capex,
            cash_taxes_paid=deal.cash_taxes_paid, distributions=deal.distributions,
            scheduled_debt_service=deal.scheduled_debt_service, annual_rent_and_leases=deal.annual_rent_and_leases,
        )
        text = (
            f"Trailing FCCR (as if tested) computes to {fccr['fccr']:.2f}x against a {deal.fccr_minimum:.2f}x "
            f"facility minimum. Current on-file risk rating is {deal.risk_rating}. No ANTHROPIC_API_KEY is "
            f"configured, so this is a deterministic summary rather than a full collateral and industry "
            f"analysis -- configure an API key for a complete underwriting narrative."
        )
        return {"agent_name": _AGENT_NAMES.get(stage_id, "Underwriting & Credit Agent"), "text": text, "citations": [], "source": "rule_based", "proposed_changes": proposed}

    text = (
        f"Reviewed deal {deal.id} at stage '{stage_id}' against on-file data. No ANTHROPIC_API_KEY is "
        f"configured, so no LLM-drafted narrative is available for this stage; the deterministic checks "
        f"available (borrowing base, FCCR, watchlist trend) run under the Servicing, Covenant, and "
        f"Portfolio Risk stages regardless of key configuration."
    )
    return {"agent_name": _AGENT_NAMES.get(stage_id, "ABL Agent"), "text": text, "citations": [], "source": "rule_based", "proposed_changes": proposed}
