"""Seeds the SQLite database with document types + key terms and seven deals
spread across the lifecycle, each with realistic pending/approved/rejected
HITL items covering every guardrail tier. Safe to re-run: drops and
recreates the database file first.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chromadb  # noqa: E402
from app import audit, config, crud, document_intake_agent  # noqa: E402
from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Base, BorrowingBaseCertificate, Deal, Document, DocumentType,
    ExtractedField, KeyTerm, PendingChange, StageEvent,
)
from app.routers.agents import LIFECYCLE_ORDER as STAGE_SEQUENCE  # noqa: E402

now = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return now - timedelta(days=n)


def mark_timeline(db, deal: Deal, up_to_stage: str, branch: str | None = None) -> None:
    idx = STAGE_SEQUENCE.index(up_to_stage)
    for i, stage in enumerate(STAGE_SEQUENCE[: idx + 1]):
        status = "completed" if i < idx else "in_progress"
        db.add(StageEvent(
            deal_id=deal.id, stage=stage, status=status,
            entered_at=days_ago(60 - i * 5), completed_at=days_ago(60 - i * 5 - 3) if status == "completed" else None,
        ))
    if branch:
        db.add(StageEvent(deal_id=deal.id, stage=branch, status="in_progress", entered_at=days_ago(3)))


def seed_document_types(db) -> dict[str, DocumentType]:
    definitions = {
        "Borrowing Base Certificate": {
            "description": "Periodic borrower-certified calculation of eligible collateral and availability.",
            "terms": [
                ("Gross Accounts Receivable", ["Gross AR", "Total Accounts Receivable"], "currency"),
                ("Eligible Accounts Receivable", ["Eligible AR"], "currency"),
                ("Inventory at Cost", ["Total Inventory"], "currency"),
                ("Borrowing Base", [], "currency"),
                ("Availability", ["Excess Availability"], "currency"),
                ("Period End Date", ["As Of Date", "Certificate Date"], "date"),
            ],
        },
        "AR Aging Report": {
            "description": "Accounts receivable aging schedule supporting the ineligibles calculation.",
            "terms": [
                ("Total Accounts Receivable", [], "currency"),
                ("Current 0-30 Days", ["0-30 Days"], "currency"),
                ("31-60 Days", [], "currency"),
                ("61-90 Days", [], "currency"),
                ("Over 90 Days", ["90+ Days"], "currency"),
                ("Largest Customer Concentration", ["Top Customer %"], "percent"),
            ],
        },
        "Financial Statements": {
            "description": "Borrower-prepared or audited periodic financial statements.",
            "terms": [
                ("Total Revenue", ["Net Sales", "Total Sales"], "currency"),
                ("EBITDA", [], "currency"),
                ("Net Income", [], "currency"),
                ("Total Debt", ["Total Liabilities"], "currency"),
                ("Cash and Equivalents", ["Cash"], "currency"),
                ("Capital Expenditures", ["Capex"], "currency"),
            ],
        },
        "Credit Agreement": {
            "description": "The negotiated facility agreement and its structuring terms.",
            "terms": [
                ("Facility Commitment", ["Total Commitment", "Revolving Credit Commitment"], "currency"),
                ("AR Advance Rate", [], "percent"),
                ("Inventory Advance Rate", [], "percent"),
                ("FCCR Minimum", ["Fixed Charge Coverage Ratio Minimum"], "text"),
                ("Maturity Date", [], "date"),
                ("Governing Law", [], "text"),
            ],
        },
        "Field Exam Report": {
            "description": "Independent verification of AR and inventory reporting accuracy.",
            "terms": [
                ("Exam Date", [], "date"),
                ("Examiner", ["Prepared By"], "text"),
                ("Exceptions Noted", ["Findings"], "text"),
                ("Recommended Reserve Adjustment", [], "currency"),
            ],
        },
        "Compliance Certificate": {
            "description": "Borrower certification of financial covenant compliance for the period.",
            "terms": [
                ("Reporting Period", ["Period Ended"], "text"),
                ("FCCR Calculated", ["Calculated FCCR"], "text"),
                ("FCCR Minimum Required", [], "text"),
                ("Covenant Compliance Status", ["Compliance Status"], "text"),
                ("Officer Certification", ["Certified By"], "text"),
            ],
        },
    }

    out = {}
    for name, spec in definitions.items():
        dt = DocumentType(name=name, description=spec["description"])
        db.add(dt)
        db.flush()
        for label, aliases, data_type in spec["terms"]:
            db.add(KeyTerm(document_type_id=dt.id, label=label, aliases=aliases, data_type=data_type, is_default=True))
        out[name] = dt
    db.flush()
    return out


def seed_documents(db, doc_types: dict[str, DocumentType], deals: dict[str, Deal]) -> None:
    bbc_text = """MERIDIAN APPAREL GROUP, INC.
Borrowing Base Certificate
Period End Date: August 14, 2026

Gross Accounts Receivable: $11,600,000
Eligible Accounts Receivable: $10,320,000
Inventory at Cost: $9,050,000
Borrowing Base: $12,876,063
Availability: $1,626,063

Certified by: Chief Financial Officer, Meridian Apparel Group, Inc.
"""
    fin_text = """VANTAGE FOODS DISTRIBUTION, INC.
Financial Statement Summary - Fiscal Year 2025

Total Revenue: $61,200,000
EBITDA: $5,875,000
Net Income: $2,140,000
Total Debt: $9,400,000
Cash and Equivalents: $1,150,000
Capital Expenditures: $610,000
"""

    def make_doc(deal_id, doc_type, filename, text, uploaded_by, all_confirmed):
        key_terms = [{"id": t.id, "label": t.label, "aliases": t.aliases, "data_type": t.data_type} for t in doc_type.key_terms]
        doc = Document(
            deal_id=deal_id, document_type_id=doc_type.id, filename=filename,
            raw_text_excerpt=text, uploaded_by=uploaded_by,
            status="processed" if all_confirmed else "pending_review",
            uploaded_at=days_ago(2 if all_confirmed else 1),
        )
        db.add(doc)
        db.flush()  # assigns doc.id, which scopes the semantic chunk search below
        candidates = document_intake_agent.run(doc.id, filename, text, key_terms)
        for c in candidates:
            db.add(ExtractedField(
                document_id=doc.id, key_term_id=c.key_term_id, label=c.label,
                extracted_value=c.value, confidence=c.confidence, match_method=c.match_method,
                status="confirmed" if all_confirmed and c.value else "pending_review",
                reviewed_by=uploaded_by if all_confirmed else "",
                reviewed_at=days_ago(2) if all_confirmed else None,
            ))
        audit.append(
            db, event_type="document_uploaded", actor=uploaded_by, deal_id=deal_id or "",
            summary=f"Uploaded {filename} as {doc_type.name}",
            detail={"document_id": doc.id, "document_type": doc_type.name},
        )
        return doc

    make_doc(deals["meridian-apparel-001"].id, doc_types["Borrowing Base Certificate"],
              "meridian_bbc_2026-08-14.txt", bbc_text, "Dana Whitfield", all_confirmed=True)
    make_doc(deals["vantage-foods-003"].id, doc_types["Financial Statements"],
              "vantage_foods_fy2025_summary.txt", fin_text, "Priya Nair", all_confirmed=False)


def build_deals(db) -> dict[str, Deal]:
    deals: dict[str, Deal] = {}

    meridian = Deal(
        id="meridian-apparel-001", borrower_name="Meridian Apparel Group, Inc.",
        industry="Wholesale apparel distribution", naics="424330", hq="Charlotte, NC", sponsor="Kestrel Capital Partners",
        commitment=15_000_000, closing_date="2024-03-15", maturity_date="2027-03-15",
        ar_advance_rate=0.85, inventory_advance_rate_nolv=0.85, inventory_cost_cap_pct=0.60,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=2_000_000,
        fccr_minimum=1.10, stage="covenant_compliance", risk_rating="Pass", watchlist=False, covenant_status="not_yet_tested",
        outstanding_balance=11_000_000, letters_of_credit=250_000,
        latest_borrowing_base=12_876_063.11, latest_availability=1_626_063.11,
        trailing_revenue=48_500_000, trailing_ebitda=4_650_000, unfinanced_capex=380_000, cash_taxes_paid=210_000,
        distributions=0, scheduled_debt_service=900_000, annual_rent_and_leases=1_150_000,
        authority_level="Credit Officer",
    )

    harbor = Deal(
        id="harbor-steel-002", borrower_name="Harbor Steel Fabricators, LLC",
        industry="Metal fabrication & structural steel", naics="332312", hq="Baytown, TX", sponsor="Independent (family-owned)",
        commitment=8_000_000, closing_date="", maturity_date="",
        ar_advance_rate=0.85, inventory_advance_rate_nolv=0.80, inventory_cost_cap_pct=0.55,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=1_000_000,
        fccr_minimum=1.10, stage="origination", risk_rating="Pass", watchlist=False,
        outstanding_balance=0, letters_of_credit=0, latest_borrowing_base=0, latest_availability=0,
        trailing_revenue=22_000_000, trailing_ebitda=2_100_000, unfinanced_capex=140_000, cash_taxes_paid=90_000,
        distributions=0, scheduled_debt_service=0, annual_rent_and_leases=310_000,
        authority_level="Credit Officer",
    )

    vantage = Deal(
        id="vantage-foods-003", borrower_name="Vantage Foods Distribution, Inc.",
        industry="Food & beverage distribution", naics="424410", hq="Fresno, CA", sponsor="Meadowbrook Partners",
        commitment=12_000_000, closing_date="", maturity_date="",
        ar_advance_rate=0.85, inventory_advance_rate_nolv=0.80, inventory_cost_cap_pct=0.55,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=1_500_000,
        fccr_minimum=1.10, stage="underwriting", risk_rating="Pass", watchlist=False,
        outstanding_balance=0, letters_of_credit=0, latest_borrowing_base=0, latest_availability=0,
        trailing_revenue=61_200_000, trailing_ebitda=5_875_000, unfinanced_capex=610_000, cash_taxes_paid=340_000,
        distributions=0, scheduled_debt_service=0, annual_rent_and_leases=780_000,
        authority_level="Credit Officer",
    )

    crestline = Deal(
        id="crestline-furniture-004", borrower_name="Crestline Furniture Co.",
        industry="Furniture manufacturing & wholesale", naics="337122", hq="High Point, NC", sponsor="Ashwood Equity Partners",
        commitment=10_000_000, closing_date="", maturity_date="",
        ar_advance_rate=0.85, inventory_advance_rate_nolv=0.75, inventory_cost_cap_pct=0.55,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=1_500_000,
        fccr_minimum=1.15, stage="documentation_closing", risk_rating="Pass", watchlist=False,
        outstanding_balance=0, letters_of_credit=0, latest_borrowing_base=0, latest_availability=0,
        trailing_revenue=27_500_000, trailing_ebitda=2_650_000, unfinanced_capex=210_000, cash_taxes_paid=140_000,
        distributions=0, scheduled_debt_service=0, annual_rent_and_leases=520_000,
        authority_level="Senior Credit Officer",
    )

    solstice = Deal(
        id="solstice-auto-005", borrower_name="Solstice Auto Parts, Inc.",
        industry="Automotive aftermarket parts distribution", naics="423120", hq="Toledo, OH", sponsor="Northfield Capital",
        commitment=20_000_000, closing_date="2023-06-01", maturity_date="2026-06-01",
        ar_advance_rate=0.83, inventory_advance_rate_nolv=0.75, inventory_cost_cap_pct=0.55,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=2_500_000,
        fccr_minimum=1.10, stage="covenant_compliance", risk_rating="Special Mention", watchlist=True, covenant_status="not_yet_tested",
        outstanding_balance=14_200_000, letters_of_credit=0, latest_borrowing_base=15_100_000, latest_availability=900_000,
        trailing_revenue=39_800_000, trailing_ebitda=2_100_000, unfinanced_capex=250_000, cash_taxes_paid=150_000,
        distributions=0, scheduled_debt_service=1_400_000, annual_rent_and_leases=650_000,
        authority_level="Senior Credit Officer",
    )

    ridgeline = Deal(
        id="ridgeline-outdoor-006", borrower_name="Ridgeline Outdoor Supply Co.",
        industry="Outdoor & recreational equipment wholesale", naics="423910", hq="Bozeman, MT", sponsor="Trailhead Capital",
        commitment=18_000_000, closing_date="2022-09-12", maturity_date="2025-09-12",
        ar_advance_rate=0.80, inventory_advance_rate_nolv=0.70, inventory_cost_cap_pct=0.50,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=2_000_000,
        fccr_minimum=1.10, stage="special_assets_workout", risk_rating="Substandard", watchlist=True, covenant_status="breach",
        outstanding_balance=16_500_000, letters_of_credit=0, latest_borrowing_base=15_800_000, latest_availability=-700_000,
        trailing_revenue=31_000_000, trailing_ebitda=850_000, unfinanced_capex=180_000, cash_taxes_paid=40_000,
        distributions=0, scheduled_debt_service=1_100_000, annual_rent_and_leases=590_000,
        authority_level="Risk Committee",
    )

    palisade = Deal(
        id="palisade-consumer-007", borrower_name="Palisade Consumer Brands, Inc.",
        industry="Consumer packaged goods", naics="311999", hq="Denver, CO", sponsor="Summit Ridge Capital",
        commitment=25_000_000, closing_date="2022-04-01", maturity_date="2026-04-01",
        ar_advance_rate=0.85, inventory_advance_rate_nolv=0.82, inventory_cost_cap_pct=0.58,
        dilution_threshold_pct=0.05, excess_availability_trigger_pct=0.10, excess_availability_trigger_floor=2_500_000,
        fccr_minimum=1.05, stage="renewal_amendment", risk_rating="Pass", watchlist=False,
        outstanding_balance=8_000_000, letters_of_credit=300_000, latest_borrowing_base=19_500_000, latest_availability=11_200_000,
        trailing_revenue=73_400_000, trailing_ebitda=8_900_000, unfinanced_capex=920_000, cash_taxes_paid=610_000,
        distributions=0, scheduled_debt_service=600_000, annual_rent_and_leases=1_400_000,
        authority_level="Credit Officer",
    )

    for d in [meridian, harbor, vantage, crestline, solstice, ridgeline, palisade]:
        db.add(d)
        deals[d.id] = d
    db.flush()
    return deals


def seed_bbc_history(db, deals: dict[str, Deal]) -> None:
    meridian_rows = [
        ("2026-07-17", 11_820_000, 10_900_000, 9_265_000, 9_050_000, 8_000_000, 4_637_600, 0.042, 0, 150_000, 13_752_600, 9_300_000, 4_202_600, False, False, ""),
        ("2026-07-24", 11_900_000, 10_920_000, 9_282_000, 9_100_000, 8_020_000, 4_649_300, 0.046, 0, 150_000, 13_781_300, 9_400_000, 4_131_300, False, False, ""),
        ("2026-07-31", 12_000_000, 10_850_000, 9_222_500, 9_150_000, 8_030_000, 4_652_000, 0.056, 65_100, 150_000, 13_659_400, 9_450_000, 3_959_400, False, False, "Dilution crosses the 5% policy threshold for the first time this quarter."),
        ("2026-08-07", 12_050_000, 10_730_000, 9_120_500, 9_180_000, 8_000_000, 4_624_000, 0.064, 150_220, 150_000, 13_444_280, 9_500_000, 3_694_280, False, False, "Fenwick Retail Group balance now fully cross-aged. Fourth consecutive week of availability decline."),
        ("2026-08-14", 11_600_000, 10_320_000, 8_772_000, 9_050_000, 7_750_000, 4_479_500, 0.0718, 225_437, 150_000, 12_876_063, 9_500_000, 3_126_063, False, False, "Fenwick Retail Group balance charged off after bankruptcy filing."),
    ]
    for i, (period, gross_ar, elig_ar, ar_avail, inv_cost, elig_inv, inv_avail, dilution, dil_res, rent_res, bb, out_bal, avail, cd, fccr_t, note) in enumerate(meridian_rows):
        db.add(BorrowingBaseCertificate(
            deal_id="meridian-apparel-001", period_end=period, gross_ar=gross_ar, eligible_ar=elig_ar,
            ar_availability=ar_avail, inventory_at_cost=inv_cost, eligible_inventory_at_cost=elig_inv,
            inventory_availability=inv_avail, dilution_pct=dilution, dilution_reserve=dil_res, rent_reserve=rent_res,
            borrowing_base=bb, outstanding_balance=out_bal, letters_of_credit=250_000, availability=avail,
            cash_dominion_active=cd, fccr_tested=fccr_t, note=note, created_at=days_ago(28 - i * 7),
        ))

    solstice_rows = [
        ("2026-07-06", 15_600_000, 13_400_000, 11_122_000, 10_100_000, 5_040_000, 6_780_000, 0.058, 42_000, 220_000, 17_680_000, 13_900_000, 3_560_000, False, False, ""),
        ("2026-07-20", 15_100_000, 12_950_000, 10_748_500, 9_950_000, 4_980_000, 6_670_000, 0.071, 176_500, 220_000, 17_022_000, 14_050_000, 2_752_000, False, False, "Dilution up sharply; one large customer dispute unresolved."),
        ("2026-08-03", 14_400_000, 12_100_000, 10_043_000, 9_700_000, 4_850_000, 6_500_000, 0.089, 471_900, 220_000, 15_951_100, 14_200_000, 1_531_100, True, True, "Excess availability trigger breached. Cash dominion and FCCR testing now active."),
    ]
    for i, (period, gross_ar, elig_ar, ar_avail, inv_cost, elig_inv, inv_avail, dilution, dil_res, rent_res, bb, out_bal, avail, cd, fccr_t, note) in enumerate(solstice_rows):
        db.add(BorrowingBaseCertificate(
            deal_id="solstice-auto-005", period_end=period, gross_ar=gross_ar, eligible_ar=elig_ar,
            ar_availability=ar_avail, inventory_at_cost=inv_cost, eligible_inventory_at_cost=elig_inv,
            inventory_availability=inv_avail, dilution_pct=dilution, dilution_reserve=dil_res, rent_reserve=rent_res,
            borrowing_base=bb, outstanding_balance=out_bal, letters_of_credit=0, availability=avail,
            cash_dominion_active=cd, fccr_tested=fccr_t, note=note, created_at=days_ago(21 - i * 7),
        ))
    db.flush()


def seed_pending_changes(db, deals: dict[str, Deal]) -> None:
    meridian = deals["meridian-apparel-001"]
    crud.create_pending_change(
        db, meridian, stage="08 - Covenant Compliance & Financial Reporting", change_type="covenant_result",
        field_path="covenant_status", new_value="breach", proposed_by="Covenant & Compliance Agent",
        rationale=(
            "Excess availability fell to $1,626,063, below the $2,000,000 springing trigger floor, so the "
            "FCCR covenant is tested this period. Trailing FCCR computes to 1.85x against a 1.10x minimum "
            "-- ratio itself is comfortable, but the trigger event still requires the compliance certificate "
            "to record this as a tested period and activate springing cash dominion."
        ),
    )
    crud.create_pending_change(
        db, meridian, stage="09 - Portfolio & Risk Monitoring", change_type="watchlist", field_path="watchlist",
        new_value="true", proposed_by="Portfolio Risk & Early Warning Agent",
        rationale="Five consecutive weeks of declining availability culminating in a customer bankruptcy write-off is a standard watchlist migration trigger.",
    )

    harbor = deals["harbor-steel-002"]
    crud.create_pending_change(
        db, harbor, stage="01 - Origination & Prospecting", change_type="field_update", field_path="commitment",
        new_value="9500000", proposed_by="Origination Agent",
        rationale="Updated AR aging from the prospect shows a larger eligible base than the initial term sheet assumed; indicative commitment revised upward.",
    )

    vantage = deals["vantage-foods-003"]
    crud.create_pending_change(
        db, vantage, stage="02 - Underwriting & Credit Approval", change_type="risk_rating", field_path="risk_rating",
        new_value="Special Mention", proposed_by="Underwriting & Credit Agent",
        rationale="Top-three customer concentration is 41% of AR, well above the 30% policy guideline for a Pass rating in this industry; recommend Special Mention pending a concentration mitigant.",
    )

    solstice = deals["solstice-auto-005"]
    crud.create_pending_change(
        db, solstice, stage="08 - Covenant Compliance & Financial Reporting", change_type="covenant_result",
        field_path="covenant_status", new_value="breach", proposed_by="Covenant & Compliance Agent",
        rationale="Trailing FCCR computes to 0.83x against a 1.10x minimum -- a covenant breach. Excess availability trigger was breached this period, so FCCR testing applies.",
    )
    crud.create_pending_change(
        db, solstice, stage="06 - Servicing & Collateral Monitoring", change_type="draw_funding",
        field_path="outstanding_balance", new_value="15400000", proposed_by="Relationship Manager (manual request)",
        rationale="Borrower requested an incremental $1,200,000 draw to cover a supplier payment.",
        context={"available_before_draw": 900_000, "requested_draw": 1_200_000},
    )

    ridgeline = deals["ridgeline-outdoor-006"]
    crud.create_pending_change(
        db, ridgeline, stage="Branch - Special Assets, Default & Workout", change_type="field_update",
        field_path="outstanding_balance", new_value="15800000", proposed_by="Special Assets / Workout Agent",
        rationale="Forced lockbox sweep under full cash dominion to cure the existing $700,000 overadvance per the forbearance term sheet.",
    )

    palisade = deals["palisade-consumer-007"]
    crud.create_pending_change(
        db, palisade, stage="10 - Renewal, Amendment & Annual Review", change_type="field_update",
        field_path="commitment", new_value="30000000", proposed_by="Renewal & Amendment Agent",
        rationale="Borrower has grown into the existing facility (average utilization 68% over the trailing year); recommend upsizing at renewal to support continued growth.",
    )
    db.flush()


def seed_historical_decisions(db, deals: dict[str, Deal]) -> None:
    crestline = deals["crestline-furniture-004"]
    change = crud.create_pending_change(
        db, crestline, stage="03-04 - Structuring, Documentation & Closing", change_type="field_update",
        field_path="ar_advance_rate", new_value="0.82", proposed_by="Documentation & Closing Agent",
        rationale="Field exam ahead of closing found a higher proportion of extended-dating invoices than the term sheet assumed; advance rate adjusted down from 85% to 82%.",
    )
    crud.apply_pending_change(db, crestline, change)
    change.status = "approved"
    change.decided_by = "Jordan Lee"
    change.decided_role = "Senior Credit Officer"
    change.decision_notes = "Consistent with field exam findings. Approved as structured."
    change.decided_at = days_ago(6)
    audit.append(
        db, event_type="human_approval", actor="Jordan Lee", deal_id=crestline.id, stage=change.stage,
        summary=f"Approved: {change.field_path} -> {change.new_value}",
        detail={"change_id": change.id, "role": "Senior Credit Officer", "notes": change.decision_notes},
    )

    ridgeline = deals["ridgeline-outdoor-006"]
    change2 = crud.create_pending_change(
        db, ridgeline, stage="Branch - Special Assets, Default & Workout", change_type="risk_rating",
        field_path="risk_rating", new_value="Doubtful", proposed_by="Special Assets / Workout Agent",
        rationale="Continued overadvance and declining collateral coverage support a further downgrade from Substandard to Doubtful.",
    )
    change2.status = "rejected"
    change2.decided_by = "Morgan Ito"
    change2.decided_role = "Risk Committee"
    change2.decision_notes = "Deferred pending an updated NOLV appraisal; do not downgrade further until the liquidation analysis is complete."
    change2.decided_at = days_ago(2)
    audit.append(
        db, event_type="human_rejection", actor="Morgan Ito", deal_id=ridgeline.id, stage=change2.stage,
        summary=f"Rejected: {change2.field_path} -> {change2.new_value}",
        detail={"change_id": change2.id, "role": "Risk Committee", "notes": change2.decision_notes},
    )
    db.flush()


def main() -> None:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    init_db()

    # Re-running the seed script generates fresh document ids, so also reset
    # the document-intake chunk collection -- otherwise old runs' chunks pile
    # up in Chroma with no Document row left to reference them.
    from app.semantic_extraction import COLLECTION_NAME as _CHUNK_COLLECTION

    _chroma_client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        _chroma_client.delete_collection(_CHUNK_COLLECTION)
    except Exception:
        pass

    db = SessionLocal()
    try:
        audit.append(db, event_type="system_init", actor="system", summary="Database seeded for demo.")

        doc_types = seed_document_types(db)
        deals = build_deals(db)

        mark_timeline(db, deals["meridian-apparel-001"], "covenant_compliance")
        mark_timeline(db, deals["harbor-steel-002"], "origination")
        mark_timeline(db, deals["vantage-foods-003"], "underwriting")
        mark_timeline(db, deals["crestline-furniture-004"], "documentation_closing")
        mark_timeline(db, deals["solstice-auto-005"], "covenant_compliance")
        mark_timeline(db, deals["ridgeline-outdoor-006"], "covenant_compliance", branch="special_assets_workout")
        mark_timeline(db, deals["palisade-consumer-007"], "renewal_amendment")

        seed_bbc_history(db, deals)
        seed_pending_changes(db, deals)
        seed_historical_decisions(db, deals)
        seed_documents(db, doc_types, deals)

        db.commit()
        print(f"Seeded {len(deals)} deals, {db.query(PendingChange).count()} pending changes, "
              f"{db.query(Document).count()} documents into {config.DB_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
