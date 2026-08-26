"""Sanity checks that don't require ANTHROPIC_API_KEY: calculation math and
ChromaDB ingestion/retrieval. Run with `python scripts/smoke_test.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abl_agents import calculations, deal_store, knowledge_base  # noqa: E402


def test_calculations():
    result = calculations.calculate_borrowing_base(
        gross_ar=11_600_000,
        ar_ineligibles={"aging_90": 520_000, "cross_aged": 410_000, "concentration": 260_000, "contra": 90_000},
        ar_advance_rate=0.85,
        inventory_at_cost=9_050_000,
        ineligible_inventory=1_300_000,
        nolv_pct_of_cost=0.68,
        inventory_advance_rate_nolv=0.85,
        inventory_cost_cap_pct=0.60,
        trailing_gross_sales=20_600_000,
        trailing_credits_discounts_writeoffs=1_480_000,
        dilution_threshold_pct=0.05,
        rent_reserve=150_000,
        facility_commitment=15_000_000,
        outstanding_balance=9_500_000,
        letters_of_credit=250_000,
        excess_availability_trigger_pct=0.10,
        excess_availability_trigger_floor=2_000_000,
        requested_draw=1_500_000,
    )
    assert result.eligible_ar == 11_600_000 - (520_000 + 410_000 + 260_000 + 90_000)
    assert round(result.dilution_pct, 4) == round(1_480_000 / 20_600_000, 4)
    print(f"eligible_ar            = {result.eligible_ar:,.0f}")
    print(f"borrowing_base         = {result.borrowing_base:,.0f}")
    print(f"availability            = {result.availability:,.0f}")
    print(f"springing_trigger_breached (post-draw check via draw_fundable_in_full) = {result.draw_fundable_in_full}")
    print(f"max_fundable_draw       = {result.max_fundable_draw:,.0f}")
    print("calculations.py OK\n")


def test_deal_store():
    deal = deal_store.get_deal("meridian-apparel-001")
    assert deal["borrower"]["name"] == "Meridian Apparel Group, Inc."
    history = deal_store.get_bbc_history("meridian-apparel-001", limit=2)
    assert len(history) == 2
    pending = deal_store.get_pending_bbc_submission("meridian-apparel-001")
    assert pending is not None
    print("deal_store.py OK\n")


def test_knowledge_base():
    count = knowledge_base.ingest(rebuild=True)
    print(f"Indexed {count} chunks.")
    hits = knowledge_base.search("What is excess availability and what does it trigger?", n_results=3)
    for h in hits:
        print(f"  [{h.source}] {h.title}  (distance={h.distance:.3f})")
    assert hits, "expected at least one retrieval hit"
    print("knowledge_base.py OK (ChromaDB retrieval working)\n")


if __name__ == "__main__":
    test_calculations()
    test_deal_store()
    test_knowledge_base()
    print("All smoke tests passed.")
