# Borrowing Base Mechanics

## Standard Formula
Borrowing Base = (Eligible Accounts Receivable x AR Advance Rate) + (Eligible Inventory x Inventory Advance Rate) - Reserves

Availability = MIN(Borrowing Base, Facility Commitment) - Outstanding Loan Balance - Outstanding Letters of Credit

## Step 1 — Determine Eligible Accounts Receivable
Start from gross accounts receivable per the borrower's aging report, then subtract, in order: invoices aged more than 90 days from invoice date; cross-aged accounts (an account debtor with more than 50% of its total balance past due, the entire balance becomes ineligible, not just the past-due portion); amounts in excess of each account debtor's concentration limit; contra/offset accounts; bill-and-hold invoices; foreign receivables without credit insurance or a letter of credit; government receivables lacking a proper assignment of claims; and related-party or affiliate receivables.

## Step 2 — Determine Eligible Inventory
Start from inventory at the lower of cost or market, exclude ineligible categories (obsolete or slow-moving stock beyond the policy threshold, work-in-process beyond an agreed cap, consigned goods, inventory held at third-party or foreign locations without a bailee waiver). Apply the inventory advance rate to the lesser of (a) eligible inventory at cost multiplied by the agreed percentage, or (b) the most recent NOLV appraisal value multiplied by the NOLV advance rate — whichever produces the lower figure, since the NOLV appraisal governs the realistic advance ceiling.

## Step 3 — Apply Reserves
Common reserves, applied as straight dollar deductions from the combined AR and inventory availability:
- **Dilution reserve** — triggered when trailing dilution exceeds the policy threshold (commonly 5%). Reserve = (dilution % - threshold %) x eligible AR.
- **Rent/landlord reserve** — where inventory is held at a leased location without a landlord waiver, a reserve equal to a set number of months' rent protects against a landlord's lien.
- **Customs/duty reserve** — for imported inventory subject to duties that could prime the lender's lien before customs clearance.
- **Bank product reserve** — covers exposure under cash management, corporate card, or hedging products provided by the lender.

## Worked Example
Gross AR: $12,000,000. Ineligibles (aging, cross-age, concentration): $1,800,000. Eligible AR: $10,200,000. AR advance rate: 85%. AR availability: $8,670,000.

Inventory at cost: $9,000,000. Ineligible inventory: $1,200,000. Eligible inventory at cost: $7,800,000, capped at 60% of cost = $4,680,000. Most recent NOLV appraisal: 68% of cost = $5,304,000. The lower of the two, $4,680,000, governs.

Combined availability before reserves: $8,670,000 + $4,680,000 = $13,350,000.

Trailing dilution: 6.4% against an eligible-AR-weighted threshold of 5% → dilution reserve = 1.4% x $10,200,000 = $142,800. Rent reserve (two uninsured leased warehouses): $180,000.

**Borrowing Base = $13,350,000 - $142,800 - $180,000 = $13,027,200.**

If the facility commitment is $15,000,000 and the outstanding balance is $9,500,000, Availability = $13,027,200 - $9,500,000 = **$3,527,200.**

## Excess Availability and Springing Triggers
Excess Availability is typically defined as the greater of a percentage of the borrowing base (commonly 10%) or a fixed dollar floor (commonly $2,000,000-$3,000,000). When excess availability falls below the trigger:
1. **Springing cash dominion** activates — the lender begins sweeping the lockbox daily rather than allowing the borrower to control receipts.
2. **The springing FCCR covenant** begins to be tested, typically requiring a minimum of 1.0x-1.1x, calculated on a trailing-twelve-month basis, for as long as the trigger condition persists.

Both typically "spring off" once excess availability has been maintained above the threshold for a specified cure period (commonly 30-60 consecutive days), returning the facility to its uncontrolled state.

## Overadvances
An overadvance occurs when the outstanding balance exceeds the calculated borrowing base. Outside of a pre-negotiated, capped overadvance sublimit (for example, a seasonal inventory-build overadvance with its own advance rate and burn-down schedule), an overadvance is an out-of-formula exposure that requires escalated credit approval and is expected to be cured promptly, typically within a small number of business days.
