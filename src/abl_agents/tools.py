"""Tool schemas (Anthropic tool-use format) and the dispatch table agents call.

Two tool families:
  - read-only tools (search/get/list/calculate) -- agents may call these freely.
  - `propose_change` -- the only way an agent can suggest a write. It never
    touches deal_store directly; it stages a change that the orchestrator
    shows a human before anything is committed (see orchestrator.py).
"""
from __future__ import annotations

from . import calculations, deal_store, knowledge_base

TOOL_SCHEMAS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the bank's ABL knowledge base (glossary, borrowing base mechanics, "
            "lifecycle playbook, covenants, field exams, governance) for grounded, citable "
            "answers. Always use this before explaining a term, formula, or policy rather "
            "than relying on general knowledge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language question or topic."},
                "n_results": {"type": "integer", "description": "Number of passages to retrieve (default 4)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_deal",
        "description": "Fetch the full current record for one deal: borrower, facility terms, financials, risk rating, history.",
        "input_schema": {
            "type": "object",
            "properties": {"deal_id": {"type": "string"}},
            "required": ["deal_id"],
        },
    },
    {
        "name": "get_bbc_history",
        "description": "Fetch the N most recent already-processed Borrowing Base Certificates for a deal, to inspect trend (availability, dilution, ineligibles over time).",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "limit": {"type": "integer", "description": "How many recent periods to return (default 5)."},
            },
            "required": ["deal_id"],
        },
    },
    {
        "name": "get_pending_bbc_submission",
        "description": "Fetch the raw, not-yet-processed Borrowing Base Certificate submission awaiting review for a deal, if one exists.",
        "input_schema": {
            "type": "object",
            "properties": {"deal_id": {"type": "string"}},
            "required": ["deal_id"],
        },
    },
    {
        "name": "calculate_borrowing_base",
        "description": (
            "Compute the borrowing base and availability from raw BBC inputs. Advance rates, "
            "dilution threshold, reserves policy, facility commitment, and the excess-availability "
            "trigger are pulled automatically from the deal's facility terms unless overridden. "
            "Optionally pass requested_draw to test whether an incremental draw is fundable in full."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "gross_ar": {"type": "number"},
                "ar_ineligibles": {
                    "type": "object",
                    "description": "Dollar amounts by ineligible category, e.g. {\"aging_90\": 500000, \"cross_aged\": 300000}.",
                },
                "inventory_at_cost": {"type": "number"},
                "ineligible_inventory": {"type": "number"},
                "nolv_pct_of_cost": {"type": "number", "description": "Latest appraisal NOLV as a fraction of cost, e.g. 0.68."},
                "trailing_gross_sales": {"type": "number"},
                "trailing_credits_discounts_writeoffs": {"type": "number"},
                "rent_reserve": {"type": "number", "description": "Optional override; defaults to 0 if omitted."},
                "outstanding_balance": {"type": "number", "description": "Optional override; defaults to the deal's current outstanding balance."},
                "requested_draw": {"type": "number", "description": "Optional incremental draw amount to stress-test against resulting availability."},
            },
            "required": [
                "deal_id", "gross_ar", "ar_ineligibles", "inventory_at_cost",
                "ineligible_inventory", "nolv_pct_of_cost", "trailing_gross_sales",
                "trailing_credits_discounts_writeoffs",
            ],
        },
    },
    {
        "name": "calculate_fccr",
        "description": "Compute the Fixed Charge Coverage Ratio from the deal's on-file trailing financials, or from overrides you supply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "ebitda": {"type": "number"},
                "unfinanced_capex": {"type": "number"},
                "cash_taxes_paid": {"type": "number"},
                "distributions": {"type": "number"},
                "scheduled_debt_service": {"type": "number"},
                "annual_rent_and_leases": {"type": "number"},
            },
            "required": ["deal_id"],
        },
    },
    {
        "name": "check_covenant_compliance",
        "description": "Determine whether the springing FCCR covenant is even tested this period, and if so whether it's in compliance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fccr": {"type": "number"},
                "fccr_minimum": {"type": "number"},
                "springing_trigger_breached": {"type": "boolean", "description": "Whether excess availability fell below the covenant trigger this period."},
            },
            "required": ["fccr", "fccr_minimum", "springing_trigger_breached"],
        },
    },
    {
        "name": "list_field_exam_history",
        "description": "List past field exam dates, types, and results for a deal.",
        "input_schema": {
            "type": "object",
            "properties": {"deal_id": {"type": "string"}},
            "required": ["deal_id"],
        },
    },
    {
        "name": "list_nolv_appraisal_history",
        "description": "List past inventory NOLV appraisal dates and results for a deal.",
        "input_schema": {
            "type": "object",
            "properties": {"deal_id": {"type": "string"}},
            "required": ["deal_id"],
        },
    },
    {
        "name": "propose_change",
        "description": (
            "Stage a proposed write to the deal record for human approval -- for example a risk "
            "rating change, a watchlist migration, a covenant test result, or an availability update. "
            "This never writes directly; it only queues the change for the human at this stage's "
            "approval gate to accept or reject. Always include a clear, evidence-based rationale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "string"},
                "field_path": {"type": "string", "description": "Dot path into the deal record, e.g. 'risk_rating' or 'financials.trailing_ebitda'."},
                "new_value": {"description": "The proposed new value."},
                "rationale": {"type": "string"},
            },
            "required": ["deal_id", "field_path", "new_value", "rationale"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOL_SCHEMAS]


def dispatch(name: str, tool_input: dict) -> tuple[dict, dict | None, list[dict]]:
    """Executes one tool call. Returns (result, staged_change_or_None, citations)."""
    if name == "search_knowledge_base":
        hits = knowledge_base.search(tool_input["query"], tool_input.get("n_results", 4))
        citations = [{"source": h.source, "title": h.title} for h in hits]
        result = {"results": [{"title": h.title, "source": h.source, "text": h.text} for h in hits]}
        return result, None, citations

    if name == "get_deal":
        return deal_store.get_deal(tool_input["deal_id"]), None, []

    if name == "get_bbc_history":
        history = deal_store.get_bbc_history(tool_input["deal_id"], tool_input.get("limit", 5))
        return {"history": history}, None, []

    if name == "get_pending_bbc_submission":
        submission = deal_store.get_pending_bbc_submission(tool_input["deal_id"])
        return {"submission": submission}, None, []

    if name == "calculate_borrowing_base":
        deal = deal_store.get_deal(tool_input["deal_id"])
        facility = deal["facility"]
        result = calculations.calculate_borrowing_base(
            gross_ar=tool_input["gross_ar"],
            ar_ineligibles=tool_input["ar_ineligibles"],
            ar_advance_rate=facility["ar_advance_rate"],
            inventory_at_cost=tool_input["inventory_at_cost"],
            ineligible_inventory=tool_input["ineligible_inventory"],
            nolv_pct_of_cost=tool_input["nolv_pct_of_cost"],
            inventory_advance_rate_nolv=facility["inventory_advance_rate_nolv"],
            inventory_cost_cap_pct=facility["inventory_cost_cap_pct"],
            trailing_gross_sales=tool_input["trailing_gross_sales"],
            trailing_credits_discounts_writeoffs=tool_input["trailing_credits_discounts_writeoffs"],
            dilution_threshold_pct=facility["dilution_threshold_pct"],
            rent_reserve=tool_input.get("rent_reserve", 0.0),
            facility_commitment=facility["commitment"],
            outstanding_balance=tool_input.get("outstanding_balance", deal["outstanding_balance"]),
            letters_of_credit=deal["letters_of_credit"],
            excess_availability_trigger_pct=facility["excess_availability_trigger_pct"],
            excess_availability_trigger_floor=facility["excess_availability_trigger_floor"],
            requested_draw=tool_input.get("requested_draw", 0.0),
        )
        return result.to_dict(), None, []

    if name == "calculate_fccr":
        deal = deal_store.get_deal(tool_input["deal_id"])
        fin = deal["financials"]

        def val(key):
            return tool_input.get(key, fin[key])

        result = calculations.calculate_fccr(
            ebitda=val("ebitda") if "ebitda" in tool_input else fin["trailing_ebitda"],
            unfinanced_capex=val("unfinanced_capex"),
            cash_taxes_paid=val("cash_taxes_paid"),
            distributions=val("distributions"),
            scheduled_debt_service=val("scheduled_debt_service"),
            annual_rent_and_leases=val("annual_rent_and_leases"),
        )
        return result, None, []

    if name == "check_covenant_compliance":
        result = calculations.check_covenant_compliance(
            fccr=tool_input["fccr"],
            fccr_minimum=tool_input["fccr_minimum"],
            springing_trigger_breached=tool_input["springing_trigger_breached"],
        )
        return result, None, []

    if name == "list_field_exam_history":
        deal = deal_store.get_deal(tool_input["deal_id"])
        return {"field_exam_history": deal.get("field_exam_history", [])}, None, []

    if name == "list_nolv_appraisal_history":
        deal = deal_store.get_deal(tool_input["deal_id"])
        return {"nolv_appraisal_history": deal.get("nolv_appraisal_history", [])}, None, []

    if name == "propose_change":
        staged = {
            "deal_id": tool_input["deal_id"],
            "field_path": tool_input["field_path"],
            "new_value": tool_input["new_value"],
            "rationale": tool_input["rationale"],
        }
        result = {"status": "staged_for_human_approval", **staged}
        return result, staged, []

    raise ValueError(f"Unknown tool: {name}")
