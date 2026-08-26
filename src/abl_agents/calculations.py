"""Deterministic ABL collateral and covenant math.

Every figure that ends up on a borrowing base certificate or a compliance
certificate is computed here in plain Python, not left to an LLM to derive.
Agents call these functions as tools; they never do the arithmetic themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class BorrowingBaseResult:
    gross_ar: float
    total_ar_ineligibles: float
    eligible_ar: float
    ar_advance_rate: float
    ar_availability: float

    inventory_at_cost: float
    ineligible_inventory: float
    eligible_inventory_at_cost: float
    nolv_pct_of_cost: float
    inventory_advance_rate_nolv: float
    inventory_cost_cap_pct: float
    inventory_availability_from_nolv: float
    inventory_availability_from_cost_cap: float
    inventory_availability: float

    dilution_pct: float
    dilution_threshold_pct: float
    dilution_reserve: float
    rent_reserve: float

    borrowing_base: float
    facility_commitment: float
    outstanding_balance: float
    letters_of_credit: float
    availability: float

    excess_availability_trigger: float
    springing_trigger_breached: bool

    requested_draw: Optional[float] = None
    availability_after_draw: Optional[float] = None
    draw_fundable_in_full: Optional[bool] = None
    max_fundable_draw: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_borrowing_base(
    gross_ar: float,
    ar_ineligibles: dict,
    ar_advance_rate: float,
    inventory_at_cost: float,
    ineligible_inventory: float,
    nolv_pct_of_cost: float,
    inventory_advance_rate_nolv: float,
    inventory_cost_cap_pct: float,
    trailing_gross_sales: float,
    trailing_credits_discounts_writeoffs: float,
    dilution_threshold_pct: float,
    rent_reserve: float,
    facility_commitment: float,
    outstanding_balance: float,
    letters_of_credit: float,
    excess_availability_trigger_pct: float,
    excess_availability_trigger_floor: float,
    requested_draw: float = 0.0,
) -> BorrowingBaseResult:
    total_ar_ineligibles = sum(ar_ineligibles.values())
    eligible_ar = gross_ar - total_ar_ineligibles
    ar_availability = eligible_ar * ar_advance_rate

    eligible_inventory_at_cost = inventory_at_cost - ineligible_inventory
    nolv_value = eligible_inventory_at_cost * nolv_pct_of_cost
    inventory_availability_from_nolv = nolv_value * inventory_advance_rate_nolv
    inventory_availability_from_cost_cap = eligible_inventory_at_cost * inventory_cost_cap_pct
    inventory_availability = min(
        inventory_availability_from_nolv, inventory_availability_from_cost_cap
    )

    dilution_pct = (
        trailing_credits_discounts_writeoffs / trailing_gross_sales
        if trailing_gross_sales
        else 0.0
    )
    dilution_reserve = 0.0
    if dilution_pct > dilution_threshold_pct:
        dilution_reserve = (dilution_pct - dilution_threshold_pct) * eligible_ar

    borrowing_base = (
        ar_availability + inventory_availability - dilution_reserve - rent_reserve
    )

    capped_base = min(borrowing_base, facility_commitment)
    availability = capped_base - outstanding_balance - letters_of_credit

    excess_availability_trigger = max(
        excess_availability_trigger_pct * borrowing_base,
        excess_availability_trigger_floor,
    )
    springing_trigger_breached = availability < excess_availability_trigger

    result = BorrowingBaseResult(
        gross_ar=gross_ar,
        total_ar_ineligibles=total_ar_ineligibles,
        eligible_ar=eligible_ar,
        ar_advance_rate=ar_advance_rate,
        ar_availability=ar_availability,
        inventory_at_cost=inventory_at_cost,
        ineligible_inventory=ineligible_inventory,
        eligible_inventory_at_cost=eligible_inventory_at_cost,
        nolv_pct_of_cost=nolv_pct_of_cost,
        inventory_advance_rate_nolv=inventory_advance_rate_nolv,
        inventory_cost_cap_pct=inventory_cost_cap_pct,
        inventory_availability_from_nolv=inventory_availability_from_nolv,
        inventory_availability_from_cost_cap=inventory_availability_from_cost_cap,
        inventory_availability=inventory_availability,
        dilution_pct=dilution_pct,
        dilution_threshold_pct=dilution_threshold_pct,
        dilution_reserve=dilution_reserve,
        rent_reserve=rent_reserve,
        borrowing_base=borrowing_base,
        facility_commitment=facility_commitment,
        outstanding_balance=outstanding_balance,
        letters_of_credit=letters_of_credit,
        availability=availability,
        excess_availability_trigger=excess_availability_trigger,
        springing_trigger_breached=springing_trigger_breached,
    )

    if requested_draw:
        availability_after_draw = availability - requested_draw
        result.requested_draw = requested_draw
        result.availability_after_draw = availability_after_draw
        result.draw_fundable_in_full = availability_after_draw >= 0
        result.max_fundable_draw = max(availability, 0.0)

    return result


def calculate_fccr(
    ebitda: float,
    unfinanced_capex: float,
    cash_taxes_paid: float,
    distributions: float,
    scheduled_debt_service: float,
    annual_rent_and_leases: float,
) -> dict:
    numerator = ebitda - unfinanced_capex - cash_taxes_paid - distributions
    fixed_charges = scheduled_debt_service + annual_rent_and_leases
    fccr = numerator / fixed_charges if fixed_charges else float("inf")
    return {
        "numerator": numerator,
        "fixed_charges": fixed_charges,
        "fccr": round(fccr, 3),
    }


def check_covenant_compliance(fccr: float, fccr_minimum: float, springing_trigger_breached: bool) -> dict:
    if not springing_trigger_breached:
        return {
            "fccr_tested_this_period": False,
            "in_compliance": True,
            "reason": "Excess availability is above the springing trigger, so the FCCR covenant is dormant this period.",
        }
    in_compliance = fccr >= fccr_minimum
    return {
        "fccr_tested_this_period": True,
        "in_compliance": in_compliance,
        "reason": (
            f"Excess availability fell below the springing trigger, so FCCR was tested: "
            f"{fccr:.2f}x against a {fccr_minimum:.2f}x minimum."
        ),
    }
